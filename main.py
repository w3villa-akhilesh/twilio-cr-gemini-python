import os
import json
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, Body
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from twilio.rest import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

# --- Pydantic Models ---
class TriggerCallRequest(BaseModel):
    phone_number: Optional[str] = None

# --- Configuration ---
PORT = int(os.getenv("PORT", "8080"))
DOMAIN = os.getenv("NGROK_URL") 
if not DOMAIN:
    raise ValueError("NGROK_URL environment variable not set.")
WS_URL = f"wss://{DOMAIN}/ws"

# Updated greeting to reflect the new model
WELCOME_GREETING = "Hi! I am a voice assistant powered by Twilio and Google Gemini. Ask me anything!"

# System prompt for Gemini
# Gemini works well with a direct instruction like this.
SYSTEM_PROMPT = """You are a helpful and friendly voice assistant. This conversation is happening over a phone call, so your responses will be spoken aloud. 
Please adhere to the following rules:
1. Provide clear, concise, and direct answers.
2. Spell out all numbers (e.g., say 'one thousand two hundred' instead of 1200).
3. Do not use any special characters like asterisks, bullet points, or emojis.
4. Keep the conversation natural and engaging."""

# --- Gemini API Initialization ---
# Get your Google API key from https://aistudio.google.com/app/apikey
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

genai.configure(api_key=GOOGLE_API_KEY)

# Configure the Gemini model. We pass the system prompt during initialization.
# gemini-2.5-flash-latest is a fast and capable model suitable for this use case.
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    system_instruction=SYSTEM_PROMPT
)

# --- Twilio Client Initialization for Outbound Calls ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio phone number
TARGET_PHONE_NUMBER = os.getenv("TARGET_PHONE_NUMBER")  # Phone number to call

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    print("Warning: Twilio credentials not set. Outbound calling will be disabled.")
    twilio_client = None
else:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# --- Scheduler Configuration ---
# CRON_SCHEDULE format: "minute hour day month day_of_week"
# Examples:
# - "0 9 * * *" = Every day at 9:00 AM
# - "0 9,17 * * *" = Every day at 9:00 AM and 5:00 PM
# - "0 9 * * 1-5" = Weekdays at 9:00 AM
# - "*/30 * * * *" = Every 30 minutes
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 9 * * *")  # Default: Daily at 9 AM
ENABLE_SCHEDULED_CALLS = os.getenv("ENABLE_SCHEDULED_CALLS", "false").lower() == "true"

# Store active chat sessions
# We will now store Gemini's chat session objects
sessions = {}

# Create FastAPI app
app = FastAPI()

# Initialize scheduler
scheduler = AsyncIOScheduler()

async def gemini_response(chat_session, user_prompt):
    """Get a response from the Gemini API and stream it."""
    response = await chat_session.send_message_async(user_prompt)
    return response.text

def make_outbound_call(to_phone_number=None):
    """
    Initiates an outbound call using Twilio.
    
    Args:
        to_phone_number: The phone number to call. If None, uses TARGET_PHONE_NUMBER from env.
    
    Returns:
        dict: Call details including call_sid
    """
    if not twilio_client:
        print("Error: Twilio client not initialized. Check your credentials.")
        return {"error": "Twilio client not configured"}
    
    target = to_phone_number or TARGET_PHONE_NUMBER
    if not target:
        print("Error: No target phone number specified.")
        return {"error": "No target phone number specified"}
    
    try:
        # The TwiML URL endpoint that Twilio will request to get instructions
        twiml_url = f"https://{DOMAIN}/twiml"
        
        print(f"Initiating outbound call from {TWILIO_PHONE_NUMBER} to {target}")
        
        call = twilio_client.calls.create(
            to=target,
            from_=TWILIO_PHONE_NUMBER,
            url=twiml_url,
            status_callback=f"https://{DOMAIN}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )
        
        print(f"Call initiated successfully. SID: {call.sid}")
        return {
            "success": True,
            "call_sid": call.sid,
            "to": target,
            "from": TWILIO_PHONE_NUMBER,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error making outbound call: {str(e)}")
        return {"error": str(e)}

def scheduled_call_job():
    """Job function that gets called by the scheduler"""
    print(f"[{datetime.now()}] Executing scheduled outbound call...")
    result = make_outbound_call()
    if result.get("success"):
        print(f"Scheduled call completed: {result['call_sid']}")
    else:
        print(f"Scheduled call failed: {result.get('error')}")

@app.post("/twiml")
async def twiml_endpoint():
    """Endpoint that returns TwiML for Twilio to connect to the WebSocket"""
    # Note: Twilio ConversationRelay has built-in TTS. We specify a provider and voice.
    # You can change 'ElevenLabs' to 'Amazon' or 'Google' if you prefer their TTS.
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
    <Connect>
    <ConversationRelay url="{WS_URL}" welcomeGreeting="{WELCOME_GREETING}" ttsProvider="ElevenLabs" voice="FGY2WhTYpPnrIDTdsKH5" />
    </Connect>
    </Response>"""
    
    return Response(content=xml_response, media_type="text/xml")

@app.post("/call-status")
async def call_status_callback(request: Request):
    """Callback endpoint to track call status updates from Twilio"""
    form_data = await request.form()
    call_status = dict(form_data)
    
    # Log the important status information
    call_sid = call_status.get('CallSid', 'Unknown')
    status = call_status.get('CallStatus', 'Unknown')
    print(f"Call status update - SID: {call_sid}, Status: {status}")
    
    return {"status": "received"}

@app.post("/trigger-call")
async def trigger_outbound_call(request: TriggerCallRequest = Body(default=TriggerCallRequest())):
    """
    Manual endpoint to trigger an outbound call.
    
    Usage:
        POST /trigger-call
        Optional JSON body: {"phone_number": "+1234567890"}
    
    If no phone_number is provided, uses TARGET_PHONE_NUMBER from environment.
    """
    if not twilio_client:
        return JSONResponse(
            status_code=503,
            content={"error": "Twilio client not configured. Check your environment variables."}
        )
    
    result = make_outbound_call(request.phone_number)
    
    if result.get("success"):
        return JSONResponse(
            status_code=200,
            content=result
        )
    else:
        return JSONResponse(
            status_code=500,
            content=result
        )

@app.get("/scheduler-status")
async def scheduler_status():
    """Check the status of the scheduler and view scheduled jobs"""
    if not scheduler.running:
        return JSONResponse(
            status_code=200,
            content={
                "scheduler_running": False,
                "scheduled_calls_enabled": ENABLE_SCHEDULED_CALLS,
                "message": "Scheduler is not running"
            }
        )
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return JSONResponse(
        status_code=200,
        content={
            "scheduler_running": True,
            "scheduled_calls_enabled": ENABLE_SCHEDULED_CALLS,
            "cron_schedule": CRON_SCHEDULE,
            "jobs": jobs
        }
    )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    call_sid = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "setup":
                call_sid = message["callSid"]
                print(f"Setup for call: {call_sid}")
                # Start a new chat session for this call
                sessions[call_sid] = model.start_chat(history=[])
                
            elif message["type"] == "prompt":
                if not call_sid or call_sid not in sessions:
                    print(f"Error: Received prompt for unknown call_sid {call_sid}")
                    continue

                user_prompt = message["voicePrompt"]
                print(f"Processing prompt: {user_prompt}")
                
                chat_session = sessions[call_sid]
                response_text = await gemini_response(chat_session, user_prompt)
                
                # The chat_session object automatically maintains history.
                
                # Send the complete response back to Twilio.
                # Twilio's ConversationRelay will handle the text-to-speech conversion.
                await websocket.send_text(
                    json.dumps({
                        "type": "text",
                        "token": response_text,
                        "last": True  # Indicate this is the full and final message
                    })
                )
                print(f"Sent response: {response_text}")
                
            elif message["type"] == "interrupt":
                print(f"Handling interruption for call {call_sid}.")
                
            else:
                print(f"Unknown message type received: {message['type']}")
                
    except WebSocketDisconnect:
        print(f"WebSocket connection closed for call {call_sid}")
        if call_sid in sessions:
            sessions.pop(call_sid)
            print(f"Cleared session for call {call_sid}")

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on application startup"""
    print("=" * 60)
    print("Application Starting Up")
    print("=" * 60)
    print(f"Server Port: {PORT}")
    print(f"Domain: {DOMAIN}")
    print(f"WebSocket URL: {WS_URL}")
    print(f"Twilio Client Configured: {'Yes' if twilio_client else 'No'}")
    
    if ENABLE_SCHEDULED_CALLS and twilio_client:
        print(f"Scheduled Calls: ENABLED")
        print(f"CRON Schedule: {CRON_SCHEDULE}")
        print(f"Target Phone: {TARGET_PHONE_NUMBER or 'Not set'}")
        
        # Add the scheduled job
        scheduler.add_job(
            scheduled_call_job,
            CronTrigger.from_crontab(CRON_SCHEDULE),
            id="scheduled_outbound_call",
            name="Scheduled Outbound Call",
            replace_existing=True
        )
        
        # Start the scheduler
        scheduler.start()
        print("Scheduler started successfully!")
        
        # Show next scheduled run
        jobs = scheduler.get_jobs()
        if jobs:
            next_run = jobs[0].next_run_time
            print(f"Next scheduled call: {next_run}")
    else:
        if not ENABLE_SCHEDULED_CALLS:
            print("Scheduled Calls: DISABLED (Set ENABLE_SCHEDULED_CALLS=true to enable)")
        else:
            print("Scheduled Calls: DISABLED (Twilio client not configured)")
    
    print("=" * 60)
    print("Server Ready!")
    print("=" * 60)
    print("\nEndpoints:")
    print(f"  - TwiML: https://{DOMAIN}/twiml")
    print(f"  - WebSocket: {WS_URL}")
    print(f"  - Trigger Call: POST https://{DOMAIN}/trigger-call")
    print(f"  - Scheduler Status: GET https://{DOMAIN}/scheduler-status")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    if scheduler.running:
        scheduler.shutdown()
        print("Scheduler stopped")

if __name__ == "__main__":
    print(f"Starting server on port {PORT}")
    print(f"WebSocket URL for Twilio: {WS_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)