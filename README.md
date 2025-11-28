# AI Voice Assistant with Twilio and Google Gemini (Python)

This project creates an AI voice assistant that uses [Twilio Voice](https://www.twilio.com/en-us/voice) and [ConversationRelay](https://www.twilio.com/en-us/products/conversational-ai/conversationrelay), and the [Google Gemini API](https://ai.google.dev/) to engage in two-way conversations over a phone call.

## Overview

This application allows users to call a Twilio number and interact with an AI assistant powered by Google's `gemini-2.5-flash` model. The assistant will respond to user queries in natural, spoken language.

**NEW:** The application now supports both **inbound** and **outbound** calls with automated scheduling capabilities!

## Prerequisites

- [Python 3.10+](https://www.python.org/downloads/)
- A Twilio Account: Sign up for a [free trial here](https://twil.io/try-twilio).
- A Twilio Number with Voice Capabilities: [Instructions to purchase a number](https://support.twilio.com/hc/en-us/articles/223180928-How-to-Buy-a-Twilio-Phone-Number).
- A Google AI API Key: Visit [Google AI Studio here](https://aistudio.google.com/) to generate a key for free.

## Installation

1. Clone this repository:

    ``` bash
    git clone https://github.com/w3villa-akhilesh/twilio-cr-gemini-python.git
    cd twilio-cr-gemini-python
    ```

2. Install the required dependencies. It's recommended to use a virtual environment.

    ``` bash
    pip install -r requirements.txt
    ```

3. Configure your environment variables by creating a `.env` file in the root of your project:

    ``` bash
    # .env file
    
    # Server Configuration
    PORT=8080
    NGROK_URL=your-ngrok-url.ngrok-free.app
    
    # Google Gemini API
    GOOGLE_API_KEY=your_google_api_key_here
    
    # Twilio Configuration (Required for Outbound Calls)
    TWILIO_ACCOUNT_SID=your_twilio_account_sid
    TWILIO_AUTH_TOKEN=your_twilio_auth_token
    TWILIO_PHONE_NUMBER=+1234567890  # Your Twilio phone number
    
    # Outbound Call Configuration
    TARGET_PHONE_NUMBER=+1234567890  # Phone number to receive scheduled calls
    
    # Scheduler Configuration (Optional)
    ENABLE_SCHEDULED_CALLS=false  # Set to 'true' to enable automated scheduled calls
    CRON_SCHEDULE=0 9 * * *  # CRON format: minute hour day month day_of_week
    ```
    
    **CRON Schedule Examples:**
    - `0 9 * * *` = Every day at 9:00 AM
    - `0 9,17 * * *` = Every day at 9:00 AM and 5:00 PM
    - `0 9 * * 1-5` = Weekdays at 9:00 AM
    - `*/30 * * * *` = Every 30 minutes
    - `0 12 * * 0` = Every Sunday at noon

## Usage

1. Start [ngrok](https://ngrok.com/) to expose your local server to the internet on port 8080:

    ``` bash
    ngrok http 8080
    ```

2. Copy the `https://` forwarding URL from your ngrok terminal and update the NGROK_URL in your `.env` file with the domain part (e.g., your-ngrok-forwarding-url.ngrok-free.app).
3. Run the application:

    ``` bash
    python main.py
    ```

4. Configure your Twilio phone number's voice webhook. In the Twilio console, navigate to your number's settings and under "A CALL COMES IN", set the webhook to your ngrok URL with the `/twiml` endpoint (e.g., https://your-ngrok-forwarding-url.ngrok-free.app/twiml).
5. Call your Twilio number and start talking to your new Gemini-powered voice assistant!

## Features

### 1. Inbound Calls
Users can call your Twilio number and have a conversation with the AI assistant.

### 2. Outbound Calls
The application can initiate calls to phone numbers in two ways:

#### A. Manual Trigger (via API)
Trigger an outbound call anytime using the REST API:

```bash
# Call the default TARGET_PHONE_NUMBER
curl -X POST https://your-ngrok-url.ngrok-free.app/trigger-call

# Call a specific number
curl -X POST https://your-ngrok-url.ngrok-free.app/trigger-call \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+1234567890"}'
```

#### B. Scheduled Calls (CRON)
Enable automated scheduled calls by setting `ENABLE_SCHEDULED_CALLS=true` in your `.env` file. The application will automatically call the `TARGET_PHONE_NUMBER` according to your `CRON_SCHEDULE`.

### 3. Scheduler Status
Check the status of your scheduled calls:

```bash
curl https://your-ngrok-url.ngrok-free.app/scheduler-status
```

This will return information about whether the scheduler is running, the current CRON schedule, and the next scheduled call time.

## How It Works

### Inbound Call Flow
1. When a user calls the Twilio number, Twilio makes an HTTP request to the `/twiml` endpoint.
2. The application returns TwiML, which instructs Twilio to establish a WebSocket connection to the server at `/ws`.
3. Voice input from the user is transcribed by Twilio and sent to the server as JSON messages over the WebSocket.
4. The server sends the transcribed text to the **Google Gemini API** and gets a response.
5. The AI-generated text response is sent back to Twilio through the WebSocket.
6. Twilio's built-in Text-to-Speech (TTS) engine converts the text to audio and plays it for the user.
7. The conversation continues until the call is disconnected.

### Outbound Call Flow
1. The application uses the Twilio REST API to initiate a call to the target phone number.
2. When the call is answered, Twilio requests the TwiML from the `/twiml` endpoint.
3. The same WebSocket conversation flow as inbound calls is established.
4. The AI assistant greets the recipient and the conversation proceeds normally.

### Scheduled Calls
1. When enabled, APScheduler runs in the background as part of the FastAPI application.
2. Based on the CRON schedule, the scheduler triggers the outbound call function.
3. The outbound call is placed automatically at the scheduled times.
4. All call attempts and results are logged to the console.

## Project Structure

- `main.py`: The main application file containing the FastAPI server, WebSocket handler, **Google Gemini integration**, Twilio outbound calling, and APScheduler for automated calls.

- `requirements.txt`: A file listing the Python dependencies including Twilio SDK and APScheduler.

- `.env`: A file for storing environment variables including API keys, Twilio credentials, and scheduler configuration.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/twiml` | Returns TwiML instructions for Twilio to establish WebSocket connection |
| WebSocket | `/ws` | WebSocket endpoint for real-time voice conversation |
| POST | `/trigger-call` | Manually trigger an outbound call (optional phone_number in JSON body) |
| GET | `/scheduler-status` | View scheduler status and next scheduled call time |
| POST | `/call-status` | Callback endpoint for Twilio call status updates |

## Configuration Options

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `PORT` | No | 8080 | Server port |
| `NGROK_URL` | Yes | - | Your ngrok domain (without https://) |
| `GOOGLE_API_KEY` | Yes | - | Google AI API key |
| `TWILIO_ACCOUNT_SID` | For outbound | - | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | For outbound | - | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | For outbound | - | Your Twilio phone number |
| `TARGET_PHONE_NUMBER` | For scheduled calls | - | Default number to call |
| `ENABLE_SCHEDULED_CALLS` | No | false | Enable/disable scheduled calls |
| `CRON_SCHEDULE` | No | 0 9 * * * | CRON expression for call schedule |

## Getting Twilio Credentials

1. Log in to your [Twilio Console](https://console.twilio.com/)
2. Find your **Account SID** and **Auth Token** on the dashboard
3. Your **Twilio Phone Number** can be found under Phone Numbers → Manage → Active numbers

## Troubleshooting

### Scheduled Calls Not Working
- Ensure `ENABLE_SCHEDULED_CALLS=true` in your `.env` file
- Verify all Twilio credentials are correctly set
- Check that `TARGET_PHONE_NUMBER` is set with country code (e.g., +1234567890)
- Check the application logs for scheduler status on startup
- Use the `/scheduler-status` endpoint to verify the scheduler is running

### Outbound Call Fails
- Verify your Twilio phone number has voice capabilities
- Ensure the target phone number is in E.164 format (+country_code + number)
- Check your Twilio account balance and trial account restrictions
- Review the application logs for detailed error messages

### Inbound Calls Not Connecting
- Verify your ngrok URL is correctly set in the `.env` file
- Ensure your Twilio phone number webhook is configured correctly
- Check that the webhook URL uses HTTPS (ngrok provides this automatically)
