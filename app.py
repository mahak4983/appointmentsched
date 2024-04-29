import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime
from database import DataStore

load_dotenv()

app = Flask(__name__)
client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))

database = DataStore()

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file(
    "credentials.json", scopes=scopes)
client = gspread.authorize(creds)
sheet_id = "1IbNZtrFE04lzN0p_4aAcDzQk7DglBPT2LB0lXpPbXK0"
workbook = client.open_by_key(sheet_id)

# Define conversation stages
CONVERSATION_STAGES = {
    'START': 'start',
    'GET_CHECK_IN_DATE': 'get_check_in_date',
    'GET_CHECK_OUT_DATE': 'get_check_out_date',
    'GET_ROOM_TYPE': 'get_room_type',
    'GET_NAME': 'get_name',
    'GET_AADHAAR_NUMBER': 'get_aadhaar_number',
    'CONFIRM_BOOKING': 'confirm_booking'
}

# Dictionary to store user's responses
user_stage = {}
user_responses = {}

# list to store all the data
data = []

# Room types and prices
ROOM_TYPES = database.get_room_types()

def respond(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)

def validate_date(date_text):
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def validate_num_guests(num_guests):
    try:
        num_guests = int(num_guests)
        if num_guests > 0:
            return True
    except ValueError:
        pass
    return False

    

def validate_room_type(room_type):
    return room_type.lower() in ROOM_TYPES.keys()

def calculate_stay_duration(check_in_date, check_out_date):
    return (check_out_date - check_in_date).days


def check_number_in_sheet(number):
    # Get all values in the first column (assuming numbers are stored in the first column)
    numbers_in_sheet = workbook.sheet1.col_values(2)

    # Extract last 10 digits from the provided number
    last_10_digits = number[-10:]
    print(numbers_in_sheet)
    
    for num in numbers_in_sheet:
        if num[-10:] == last_10_digits:
            return True  # Number is found in the sheet

    return False

@app.route('/message', methods=['POST'])
def reply():
    sender_number = request.form.get('From')

    message = request.form.get('Body').lower()

    current_stage = user_stage.get(sender_number, CONVERSATION_STAGES['START'])

    if current_stage == CONVERSATION_STAGES['START']:
        user_stage[sender_number] = CONVERSATION_STAGES['GET_CHECK_IN_DATE']
        user_responses[sender_number] = {}
        return respond(f"Welcome! Are you reaching out for appointment by {sender_number} number")

    elif current_stage == CONVERSATION_STAGES['GET_CHECK_IN_DATE']:
        if message.upper() == 'RESTART':
            user_stage[sender_number] = CONVERSATION_STAGES['START']
        if message.upper() =='YES':
            if check_number_in_sheet(sender_number):
                return respond("Your number is already registered.")
            else:
                return respond(f"Sure, let's schedule your appointment {sender_number}")
        else :
            return respond("Let us know what else we can help you with")
            
        # if validate_date(message):
        #     user_stage[sender_number] = CONVERSATION_STAGES['GET_CHECK_OUT_DATE']
        #     user_responses[sender_number]['check-in-date'] = message
            
        #     return respond("Great! Please enter your check-out date (YYYY-MM-DD).")
        # else:
        #     return respond("Invalid date format. Please enter the check-in date in YYYY-MM-DD format.")

    elif current_stage == CONVERSATION_STAGES['GET_CHECK_OUT_DATE']:
        if message.upper() == 'RESTART' or message.upper() == 'RESTART':
            user_stage[sender_number] = CONVERSATION_STAGES['START']
        if validate_date(message):
            check_in_date = datetime.strptime(
                user_responses[sender_number]['check-in-date'],
                r'%Y-%m-%d'
                )
            check_out_date = datetime.strptime(message, r'%Y-%m-%d')
            stay_duration = calculate_stay_duration(check_in_date, check_out_date)
            if stay_duration > 0:
                user_stage[sender_number] = CONVERSATION_STAGES['GET_ROOM_TYPE']
                user_responses[sender_number]['check-out-date'] = message
                user_responses[sender_number]['duration'] = stay_duration

                # Check available rooms from database
                room_types_str = '\n'.join([f"- {room_type.capitalize()}: Rs. {obj['price']}" for room_type, obj in ROOM_TYPES.items()])
                return respond(f"Your stay duration is {stay_duration} days. Please choose from the following room types:\n{room_types_str}")
            else:
                return respond("Invalid check-out date. Check-out date must be after check-in date.")
        else:
            return respond("Invalid date format. Please enter the check-out date in YYYY-MM-DD format.")


    elif current_stage == CONVERSATION_STAGES['GET_ROOM_TYPE']:
        if message.upper() == 'RESTART' or message.upper() == 'RESTART':
            user_stage[sender_number] = CONVERSATION_STAGES['START']
        room_type = message.lower()
        if validate_room_type(room_type):
            user_stage[sender_number] = CONVERSATION_STAGES['GET_NAME']
            user_responses[sender_number]['room-type'] = room_type
            return respond(f"Great choice! Please enter your name:")
        else:
            room_types_str = '\n'.join([f"- {room_type.capitalize()}: ${obj['price']}" for room_type, obj in ROOM_TYPES.items()])
            return respond(f"Invalid room type. Please choose from the following room types:\n{room_types_str}")
    
    elif current_stage == CONVERSATION_STAGES['GET_NAME']:
            user_stage[sender_number] = CONVERSATION_STAGES['GET_AADHAAR_NUMBER']
            user_responses[sender_number]['name'] = message.upper()
            return respond("Thank you! Please enter your Aadhaar number:")
    
    elif current_stage == CONVERSATION_STAGES['GET_AADHAAR_NUMBER']:
            user_stage[sender_number] = CONVERSATION_STAGES['CONFIRM_BOOKING']
            user_responses[sender_number]['adhaar'] = message

            name = user_responses[sender_number]['name']
            check_in_date = user_responses[sender_number]['check-in-date']
            check_out_date = user_responses[sender_number]['check-out-date']
            room_type = user_responses[sender_number]['room-type']
            price = ROOM_TYPES[room_type]['price']*user_responses[sender_number]['duration']

            response_str = f"Name: {name}\n"\
                            f"Check-in Date: {check_in_date}\n"\
                            f"Check-out Date: {check_out_date}\n"\
                            f"Room Type: {room_type}\n"\
                            f"Total Price: Rs. {price}\n"
            return respond(f"Got it! Please confirm your booking details by entering Yes.\n{response_str}")

    elif current_stage == CONVERSATION_STAGES['CONFIRM_BOOKING']:
        if message.upper() == 'Y' or message.upper() == 'YES':
            user_stage[sender_number] = CONVERSATION_STAGES['START']

            # Update the database
            name = user_responses[sender_number]['name']
            check_in_date = user_responses[sender_number]['check-in-date']
            check_out_date = user_responses[sender_number]['check-out-date']
            room_type = user_responses[sender_number]['room-type']
            duration = user_responses[sender_number]['duration']
            amount = ROOM_TYPES[room_type]['price']*duration
            aadhar = user_responses[sender_number]['adhaar']
            number = sender_number

            database.add_booking(name, check_in_date, check_out_date, room_type,duration, amount,  aadhar, number)

            return respond("Your booking is confirmed. Thank you!")
        elif message.upper == 'N' or message.upper() == 'NO':
            user_stage[sender_number] = CONVERSATION_STAGES['START']
            return respond("Your booking has been cancelled.\nWelcome! Please enter your check-in date (YYYY-MM-DD).")
        return respond("Please enter Y or Yes to confirm or No to cancel")

if __name__ == '__main__':
    app.run(debug=True)
