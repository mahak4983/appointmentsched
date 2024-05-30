import os
import gspread
import json
import aiohttp
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import requests
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime, timedelta
from database import DataStore
import urllib.parse
import re
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config.from_object('config.Config')

db = SQLAlchemy(app)
client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))


class Appointments(db.Model):
    __tablename__ = 'appointments'

    name = db.Column(db.String(100), primary_key=True)
    number = db.Column(db.String(15), primary_key=True)
    appointmentStatus = db.Column(db.Enum('yes', 'no'), nullable=False)
    appointmentDate = db.Column(db.String(10), nullable=False)
    appointmentTime = db.Column(db.String(8), nullable=False)
    doctor = db.Column(db.String(100), nullable=False)
    ailment = db.Column(db.String(255))
    location = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f'<Appointment {self.name} - {self.number}>'

# Sheet Integration
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file(
    "credentials.json", scopes=scopes)
client = gspread.authorize(creds)
sheet_id = "1IbNZtrFE04lzN0p_4aAcDzQk7DglBPT2LB0lXpPbXK0"
workbook = client.open_by_key(sheet_id)
sheet = workbook.sheet1

# Calendar Integration
scopes_calendar = ["https://www.googleapis.com/auth/calendar.events"]
creds_calendar = Credentials.from_service_account_file(
    'credentials.json',
    scopes=scopes_calendar
)
service_calendar = build('calendar', 'v3', credentials=creds_calendar)

# Define conversation stages
CONVERSATION_STAGES = {
    'START': 'start',
    'VALIDATE_YES_NO': 'validate_yes_no',
    'VALIDATE_SCHED_OR_OTHER': 'validate_sched_or_other',
    'SCHEDULE_OTHERS': 'schedule_others',
    'ENTER_NAME': 'enter_name',
    'SCHED_APPOINT_DATE': 'sched_appoint_DATE',
    'SCHED_APPOINT_TIME': 'sched_appoint_time',
    'DOCTOR': 'doctor',
    'LOCATION': 'location',
    'AILMENT':'ailment',
    'RESCHED_APPOINT_DATE': 'resched_appoint_DATE',
    'RESCHED_APPOINT_TIME': 'resched_appoint_time',
    'CONFIRM_BOOKING': 'confirm_booking',
    'RECONFIRM_BOOKING': 'reconfirm_booking'
}

# Dictionary to store user's responses
user_stage = {}
user_responses = {}
sheet_data = sheet.get_all_values()

# list to store all the data
data = []

url = "https://api.gupshup.io/wa/api/v1/msg"

headers = {
    "accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
    "apikey": "imp3qyddxoncujdnjekrs1d7abqkwovf"
}


def check_number_in_sheet(number):
    # Get all values in the first column (assuming numbers are stored in the first column)
    # numbers_in_sheet = workbook.sheet1.col_values(2)

    # # Extract last 10 digits from the provided number
    # last_10_digits = number[-10:]
    
    # for num in numbers_in_sheet:
    #     if num[-10:] == last_10_digits:
    #         return True  # Number is found in the sheet

    # return False
    appointment = Appointments.query.filter_by(number=number).first()
    if appointment:
        return True
    else:
        return False


def find_available_slots(date_str):
    print(date_str)
    date_cell_list = []
    time_values_notbooked=[]
    # Find rows with the provided date in the format '03, May'
    for row in sheet_data:
        if row[3] == date_str:  # Assuming date is in the 4th column (index 3)
            date_cell_list.append(str(row[4]))
    
    time_range = ['10AM', '11AM', '12PM', '1PM', '2PM',
                  '3PM', '4PM', '5PM', '6PM', '7PM', '8PM']


# Loop through the time range and check if each slot is booked or not
    for i in range(len(time_range) - 1):  # Exclude the last slot as it's the end time
    # Generate time slot string
        time_slot = f'{time_range[i]}-{time_range[i + 1]}'
        if time_slot not in date_cell_list:  # Check if the time slot is not booked
            time_values_notbooked.append(time_slot)
    return time_values_notbooked


def check_appointment_status(number):
    # Open the Google Sheet by its title
    # Replace 'Your Google Sheet Name' with your actual sheet name
   

    # Get all values in the first column (assuming numbers are stored in the first column)
    numbers_in_sheet = sheet.col_values(2)

    # Find the index of the number in the sheet
    if number in numbers_in_sheet:
        index = numbers_in_sheet.index(number)
        # Get the appointment status from the 3rd column (index 2 in Python)
        # Adding 1 because Google Sheets index starts from 1
        appointment_status = sheet.cell(index + 1, 3).value
        print(appointment_status)
        return appointment_status
    else:
        return "Number not found in the sheet"


@app.route('/appointments')
def get_appointments():
    # Query the appointments table
    appointments = Appointments.query.all()
    results = []
    for appointment in appointments:
        result = {
            "name": appointment.name,
            "number": appointment.number,
            "appointmentStatus": appointment.appointmentStatus,
            "appointmentDate": appointment.appointmentDate,
            "appointmentTime": appointment.appointmentTime,
            "doctor": appointment.doctor,
            "ailment": appointment.ailment,
            "location": appointment.location
        }
        results.append(result)
    return jsonify(results)

@app.route('/message', methods=['POST'])
def reply():
    response = None
    # response = requests.post(url, data=encoded_data, headers=headers)
    raw_data = request.get_data(as_text=True)

    # print(raw_data)

    # Parse the raw data into a Python dictionary
    data_dict = json.loads(raw_data)

    # Extract the value associated with the "type" key
    type_value = data_dict.get("type")

    # Print or use the extracted value
    if type_value == "message":
        sender_number=data_dict.get("payload", {}).get("sender", {}).get("phone")
        current_stage = user_stage.get(
            sender_number, CONVERSATION_STAGES['START'])
        name_value = data_dict.get("payload", {}).get("sender", {}).get("name")
        if current_stage == CONVERSATION_STAGES['START']:
            data_yes_no = {
                'channel': 'whatsapp',
                'source': '917834811114',
                'destination': f'{sender_number}',
                'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Hi {name_value}, We are excited to welcome you to ABC Clinic! Are you reaching out for appointment on your {sender_number} number","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Yes"}},{{"type":"text","title":"No"}}]}}',
                'src.name': 'schedulingbot',
            }
            encoded_data = urllib.parse.urlencode(data_yes_no)
            response = requests.post(url, data=encoded_data, headers=headers)
            user_stage[sender_number] = CONVERSATION_STAGES['VALIDATE_YES_NO']
        elif current_stage == CONVERSATION_STAGES['VALIDATE_YES_NO']:
            if data_dict['payload']['type'] == 'button_reply':
                if data_dict['payload']['payload']['title'].lower() == 'yes':
                    if check_number_in_sheet(sender_number): 
                        if(check_appointment_status(sender_number).lower()=='yes'):
                            print("active")
                            data_schedule_clinic = {
                                'channel': 'whatsapp',
                                'source': '917834811114',
                                'destination': f'{sender_number}',
                                'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"It looks like you have an upcoming appointment with us. How may we assist you further?","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"ReSchedule"}},{{"type":"text","title":"Talk to Clinic"}}]}}',
                                'src.name': 'schedulingbot',
                            }
                            user_stage[sender_number] = CONVERSATION_STAGES['RESCHED_APPOINT_DATE']
                            
                            
                        else:  
                            data_schedule_clinic = {
                           'channel': 'whatsapp',
                           'source': '917834811114',
                           'destination': f'{sender_number}',
                           'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Welcome back! How would you like to continue","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Schedule Appointment"}},{{"type":"text","title":"Talk to Clinic"}}]}}',
                           'src.name': 'schedulingbot',
                            }
                            user_stage[sender_number] = CONVERSATION_STAGES['LOCATION']
                            
                        encoded_data = urllib.parse.urlencode(
                            data_schedule_clinic)
                        response = requests.post(
                            url, data=encoded_data, headers=headers)
                        #Chane this
                    else: 
                    #    row_to_add = [name_value, sender_number, 'no']
                    #    sheet.append_row(row_to_add)
                    #    new_appointment = Appointments(
                    #     name=name_value,
                    #     number=sender_number,
                    #     appointmentStatus='no',
                    #     appointmentDate='',  # You need to set this or handle appropriately
                    #     appointmentTime='',  # You need to set this or handle appropriately
                    #     doctor='',           # You need to set this or handle appropriately
                    #     ailment='',          # You can set this as None if nullable
                    #     location=''          # You need to set this or handle appropriately
                    #    )
                    #    db.session.add(new_appointment)
                    #    db.session.commit()
                       data_schedule_clinic = {
                           'channel': 'whatsapp',
                           'source': '917834811114',
                           'destination': f'{sender_number}',
                           'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"How would you like to continue","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Schedule Appointment"}},{{"type":"text","title":"Talk to Clinic"}},{{"type":"text","title":"Schedule for other"}}]}}',
                           'src.name': 'schedulingbot',
                       }
                       encoded_data = urllib.parse.urlencode(
                           data_schedule_clinic)
                       response = requests.post(
                           url, data=encoded_data, headers=headers)
                       user_stage[sender_number] = CONVERSATION_STAGES['VALIDATE_SCHED_OR_OTHER']


                elif data_dict['payload']['payload']['title'].lower() == 'no':   
                    data = {
                        "channel": "whatsapp",
                        "source": "917834811114",
                        "destination": f'{sender_number}',
                        "src.name": "schedulingbot",
                        "message": {
                            "type": "text",
                            "text": "Please Contact the Clinic for other queries!"
                        }
                    }
                    encoded_data = urllib.parse.urlencode(data)
                    response = requests.post(
                        url, data=encoded_data, headers=headers)
                    user_stage[sender_number] = CONVERSATION_STAGES['SCHED_APPOINT_DATE']
            else:
                data = {
                    "channel": "whatsapp",
                    "source": "917834811114",
                    "destination": f'{sender_number}',
                    "src.name": "schedulingbot",
                    'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Invalid Format","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Yes"}},{{"type":"text","title":"No"}}]}}'
                }
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['VALIDATE_YES_NO']
        elif current_stage == CONVERSATION_STAGES['VALIDATE_SCHED_OR_OTHER']: 
            if data_dict['payload']['type'] == 'button_reply':
                if data_dict['payload']['payload']['title'].lower() == 'Schedule Appointment':
                    data = {
                        "channel": "whatsapp",
                        "source": "917834811114",
                        "destination": f'{sender_number}',
                        "src.name": "schedulingbot",
                        'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Select location","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Park St"}},{{"type":"text","title":"Lake View"}}]}}'
                    }
                    user_stage[sender_number] = CONVERSATION_STAGES['DOCTOR']
                elif data_dict['payload']['payload']['title'].lower() == 'Schedule for other':
                    data = {
                        'channel': 'whatsapp',
                        'source': '917834811114',
                        'destination': '91',
                        'message': '{"type":"text","text":"Enter Name"}',
                        'src.name': 'schedulingbot',
                    }
                    user_stage[sender_number] = CONVERSATION_STAGES['ENTER_NAME']
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                
        elif current_stage == CONVERSATION_STAGES['ENTER_NAME']: 
            print(data_dict)
            data = {
                "channel": "whatsapp",
                "source": "917834811114",
                "destination": f'{sender_number}',
                "src.name": "schedulingbot",
                'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Select location","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Park St"}},{{"type":"text","title":"Lake View"}}]}}'
            }
            encoded_data = urllib.parse.urlencode(data)
            response = requests.post(
                url, data=encoded_data, headers=headers)
            user_stage[sender_number] = CONVERSATION_STAGES['DOCTOR']
        elif current_stage == CONVERSATION_STAGES['LOCATION']:
            if data_dict['payload']['type'] == 'button_reply':
                data = {
                    "channel": "whatsapp",
                    "source": "917834811114",
                    "destination": f'{sender_number}',
                    "src.name": "schedulingbot",
                    'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Select location","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Park St"}},{{"type":"text","title":"Lake View"}}]}}'
                }
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['DOCTOR']
        elif current_stage == CONVERSATION_STAGES['DOCTOR']:
            
            if data_dict['payload']['type'] == 'button_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'location' in inner_dict:
                        inner_dict['location'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['location'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'location': data_dict['payload']['payload']['title']}
                print(user_responses[sender_number]['location'])
                data = {
                    "channel": "whatsapp",
                    "source": "917834811114",
                    "destination": f'{sender_number}',
                    "src.name": "schedulingbot",
                    'message': f'{{"type":"quick_reply","content":{{"type":"text","text":"Select the Doctor you want to visit","caption":"Select anyone of the options"}},"options":[{{"type":"text","title":"Dr Navin"}},{{"type":"text","title":"Dr abc"}}]}}'
                }
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['AILMENT']
        elif current_stage == CONVERSATION_STAGES['AILMENT']:

            if data_dict['payload']['type'] == 'button_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'doctor' in inner_dict:
                        inner_dict['doctor'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['doctor'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'doctor': data_dict['payload']['payload']['title']}
                print(user_responses[sender_number]['doctor'])
                data = {
                    "channel": "whatsapp",
                    "source": "917834811114",
                    "destination": f'{sender_number}',
                    "src.name": "schedulingbot",
                    'message': '{"type":"list","title":"Select Ailment","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Main Menu"}],"items":[{"title":"Select Ailment","options":[{"type":"text","title":"Root Canal"},{"type":"text","title":"Regular Checkup"}]}]}'
                }
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['SCHED_APPOINT_DATE']
        

        elif current_stage == CONVERSATION_STAGES['SCHED_APPOINT_DATE']: 
            if data_dict['payload']['type'] == 'list_reply':
                
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number] 
                    if 'ailment' in inner_dict:
                        inner_dict['ailment'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['ailment'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'ailment': data_dict['payload']['payload']['title']}
                print(user_responses[sender_number]['ailment'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"list","title":"Select Date","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Date Pciker"}],"items":[{"title":"first Section","subtitle":"first Subtitle","options":[]}]}',
                    'src.name': 'schedulingbot',
                }
                message_data = json.loads(data['message'])


                # Get today's date
                today = datetime.now().date()

                # Add dynamic date values to the "options" array in the JSON message
                for i in range(5):
                    # Calculate the date for the current iteration
                    next_date = today + timedelta(days=i)

                    # Format the date as "date, month"
                    formatted_date = next_date.strftime("%d, %B")

                    # Create a new option dictionary with dynamic date values
                    option = {
                        "type": "text",
                        "title": formatted_date,
                    }

                    # Add the option to the "options" array in the JSON message
                    message_data["items"][0]["options"].append(option)

                # Convert the updated message data back to a JSON string
                updated_message = json.dumps(message_data)

                # Update the 'message' key in the data dictionary with the updated JSON message
                data['message'] = updated_message
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['SCHED_APPOINT_TIME']
                # elif data_dict['payload']['payload']['title'] == 'Talk to Clinic':
                #     data = {
                #         "channel": "whatsapp",
                #         "source": "917834811114",
                #         "destination": f'{sender_number}',
                #         "src.name": "schedulingbot",
                #         "message": {
                #             "type": "text",
                #             "text": "Please Contact the Clinic for other queries!"
                #         }
                #     }
                #     encoded_data = urllib.parse.urlencode(data)
                #     response = requests.post(
                #         url, data=encoded_data, headers=headers)
                #     user_stage[sender_number] = CONVERSATION_STAGES['START']
        elif current_stage == CONVERSATION_STAGES['SCHED_APPOINT_TIME']:
            if data_dict['payload']['type'] == 'list_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'date' in inner_dict:
                        inner_dict['date'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['date'] = data_dict['payload']['payload']['title']


                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'date': data_dict['payload']['payload']['title']}
                print(data_dict['payload']['payload']['title'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"list","title":"Select Time","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Date Pciker"}],"items":[{"title":"first Section","subtitle":"first Subtitle","options":[]}]}',
                    'src.name': 'schedulingbot',
                }


                # Parse the JSON message from the data dictionary
                message_data = json.loads(data['message'])

                # Define the start and end times (in 24-hour format)
                start_time = 10
                end_time = 20  # 8PM in 24-hour format
 
                # Add time range options to the "options" array in the JSON message
                for hour in range(start_time, end_time):
                    # Format the time range
                    if hour < 12:
                        time_range = f"{hour}AM-{hour+1}AM"
                    elif hour == 12:
                        time_range = f"{hour}PM-{hour-11}PM"
                    else:
                        time_range = f"{hour-12}PM-{hour-11}PM"

                    # Create a new option dictionary with dynamic time values
                    option = {
                        "type": "text",
                        "title": time_range,
                    }

                    # Add the option to the "options" array in the JSON message
                    message_data["items"][0]["options"].append(option)

                # Convert the updated message data back to a JSON string
                updated_message = json.dumps(message_data)

                time_values_notbooked = find_available_slots(user_responses[sender_number]['date'])
                print(time_values_notbooked)

                options_list = [{"title": time_value}
                                for time_value in time_values_notbooked]
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': json.dumps({
                        "type": "list",
                        "title": "Select Time",
                        "body": "Click Main Menu",
                        "globalButtons": [{"type": "text", "title": "Date Picker"}],
                        "items": [{"title": "first Section", "subtitle": "first Subtitle", "options": options_list}]
                    }),
                    'src.name': 'schedulingbot',
                }

                # Update the 'message' key in the data dictionary with the updated JSON message
                # data['message'] = updated_message
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['CONFIRM_BOOKING']
        elif current_stage == CONVERSATION_STAGES['RESCHED_APPOINT_DATE']:
            # if data_dict['payload']['type'] == 'button_reply':

            #     if sender_number in user_responses:
            #         # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
            #         inner_dict = user_responses[sender_number]
            #         if 'ailment' in inner_dict:
            #             inner_dict['ailment'] = data_dict['payload']['payload']['title']
            #         else:
            #             # If 'date' doesn't exist, add it to the inner dictionary
            #             inner_dict['ailment'] = data_dict['payload']['payload']['title']

            #     else:
            #         # If sender_number doesn't exist, create a new entry with 'date'
            #         user_responses[sender_number] = {
            #             'ailment': data_dict['payload']['payload']['title']}
            #     print(user_responses[sender_number]['ailment'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"list","title":"Select Date to which you want to Reschedule to","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Date Pciker"}],"items":[{"title":"first Section","subtitle":"first Subtitle","options":[]}]}',
                    'src.name': 'schedulingbot',
                }
                message_data = json.loads(data['message'])

                # Get today's date
                today = datetime.now().date()

                # Add dynamic date values to the "options" array in the JSON message
                for i in range(5):
                    # Calculate the date for the current iteration
                    next_date = today + timedelta(days=i)

                    # Format the date as "date, month"
                    formatted_date = next_date.strftime("%d, %B")

                    # Create a new option dictionary with dynamic date values
                    option = {
                        "type": "text",
                        "title": formatted_date,
                    }

                    # Add the option to the "options" array in the JSON message
                    message_data["items"][0]["options"].append(option)

                # Convert the updated message data back to a JSON string
                updated_message = json.dumps(message_data)

                # Update the 'message' key in the data dictionary with the updated JSON message
                data['message'] = updated_message
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['RESCHED_APPOINT_TIME']
                # elif data_dict['payload']['payload']['title'] == 'Talk to Clinic':
                #     data = {
                #         "channel": "whatsapp",
                #         "source": "917834811114",
                #         "destination": f'{sender_number}',
                #         "src.name": "schedulingbot",
                #         "message": {
                #             "type": "text",
                #             "text": "Please Contact the Clinic for other queries!"
                #         }
                #     }
                #     encoded_data = urllib.parse.urlencode(data)
                #     response = requests.post(
                #         url, data=encoded_data, headers=headers)
                #     user_stage[sender_number] = CONVERSATION_STAGES['START']
        elif current_stage == CONVERSATION_STAGES['RESCHED_APPOINT_TIME']:
            if data_dict['payload']['type'] == 'list_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'date' in inner_dict:
                        inner_dict['date'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['date'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'date': data_dict['payload']['payload']['title']}
                print(data_dict['payload']['payload']['title'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"list","title":"Select Time","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Date Pciker"}],"items":[{"title":"first Section","subtitle":"first Subtitle","options":[]}]}',
                    'src.name': 'schedulingbot',
                }

                # Parse the JSON message from the data dictionary
                message_data = json.loads(data['message'])

                # Define the start and end times (in 24-hour format)
                start_time = 10
                end_time = 20  # 8PM in 24-hour format

                # Add time range options to the "options" array in the JSON message
                for hour in range(start_time, end_time):
                    # Format the time range
                    if hour < 12:
                        time_range = f"{hour}AM-{hour+1}AM"
                    elif hour == 12:
                        time_range = f"{hour}PM-{hour-11}PM"
                    else:
                        time_range = f"{hour-12}PM-{hour-11}PM"

                    # Create a new option dictionary with dynamic time values
                    option = {
                        "type": "text",
                        "title": time_range,
                    }

                    # Add the option to the "options" array in the JSON message
                    message_data["items"][0]["options"].append(option)

                # Convert the updated message data back to a JSON string
                updated_message = json.dumps(message_data)
                print(user_responses[sender_number]['date'])
                time_values_notbooked = find_available_slots(
                    user_responses[sender_number]['date'])
                print(time_values_notbooked)

                options_list = [{"title": time_value}
                                for time_value in time_values_notbooked]
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': json.dumps({
                        "type": "list",
                        "title": "Select Time",
                        "body": "Click Main Menu",
                        "globalButtons": [{"type": "text", "title": "Date Picker"}],
                        "items": [{"title": "first Section", "subtitle": "first Subtitle", "options": options_list}]
                    }),
                    'src.name': 'schedulingbot',
                }

                # Update the 'message' key in the data dictionary with the updated JSON message
                # data['message'] = updated_message
                encoded_data = urllib.parse.urlencode(data)
                response = requests.post(
                    url, data=encoded_data, headers=headers)
                user_stage[sender_number] = CONVERSATION_STAGES['RECONFIRM_BOOKING']
        elif current_stage == CONVERSATION_STAGES['CONFIRM_BOOKING']:
            if data_dict['payload']['type'] == 'list_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'time' in inner_dict:
                        inner_dict['time'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['time'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'time': data_dict['payload']['payload']['title']}
                print(data_dict['payload']['payload']['title'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"text","text":"Thanks for confirmation"}',
                    'src.name': 'schedulingbot',
                }

                print(user_responses)
               
                dynamic_date = user_responses[sender_number]['date']
                dynamic_time = user_responses[sender_number]['time']
                doctor = user_responses[sender_number]['doctor']
                ailment = user_responses[sender_number]['ailment']
                location = user_responses[sender_number]['location']


                # Update the 'message' key in the data dictionary with the dynamic value
                data['message'] = f'{{"type":"text","text":"Thanks for Booking an Appointment with us. Your appointment is schedules for: {dynamic_date} at {dynamic_time} with {doctor} at our {location} clinic for {ailment}"}}'

                # Parse the JSON message from the data dictionary
                print(data)
                input_string = user_responses[sender_number]['date']+ ', ' + user_responses[sender_number]['time'] 
                match = re.match(
                    r'(\d{1,2}), (\w+), (\d{1,2})([AP]M)-(\d{1,2})([AP]M)', input_string)

                if match:
                    day_str = match.group(1)
                    month_str = match.group(2)
                    start_time_str = match.group(3) + match.group(4)
                    end_time_str = match.group(5) + match.group(6)
                else:
                    print("Invalid input format.")
                    exit()

                # Convert month string to month number
                month_dict = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                              'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
                if month_str in month_dict:
                    month = month_dict[month_str]
                else:
                    print("Invalid month.")
                    exit()

                # Convert date, start time, and end time strings to datetime objects
                event_date = datetime(
                    year=datetime.now().year, month=month, day=int(day_str))
                start_time = datetime.strptime(start_time_str, '%I%p')
                end_time = datetime.strptime(end_time_str, '%I%p')

                # Update date and time with parsed values
                event_start = event_date.replace(
                    hour=start_time.hour if start_time.hour != 12 else 0, minute=start_time.minute)
                event_end = event_date.replace(
                    hour=end_time.hour if end_time.hour != 12 else 0, minute=end_time.minute)
                print(event_start.isoformat())
                attendees = ['resuwise@gmail.com', 'mahak4983@gmail.com']

                # Define event details
                event = {
                    'summary': f' Appointment with {sender_number}',
                    'start': {
                        'dateTime': event_start.isoformat(),
                        'timeZone': 'Asia/Kolkata',  # Specify your timezone
                    },
                    'end': {
                        'dateTime': event_end.isoformat(),
                        'timeZone': 'Asia/Kolkata',
                    },
                     #'attendees': [{'email': email} for email in attendees],
                }

                # Insert the event into Google Calendar
                created_event = service_calendar.events().insert(
                    calendarId='resuwise@gmail.com', body=event).execute()

                print('Event created:', created_event.get('htmlLink'))
                response = requests.post(
                    url, data=data, headers=headers)
                values = sheet.get_all_values()
                for row_num, row_values in enumerate(values, start=1):
                    if row_values and row_values[1] == sender_number:
                        # Update the value in the 3rd column (index 2) to 'yes'
                        sheet.update_cell(row_num, 3, 'yes')
                        # Update the value in the 4th column (index 3) with the date
                        sheet.update_cell(row_num, 4, dynamic_date)
                        # Update the value in the 4th column (index 3) with the time value
                        sheet.update_cell(row_num, 5, dynamic_time)

                        sheet.update_cell(row_num, 6, doctor)

                        sheet.update_cell(row_num, 7, ailment)

                        sheet.update_cell(row_num, 8, location)
                        print(
                            f"Updated 'yes' and date/time for mobile number {sender_number} in row {row_num}.")
                        break
                user_stage[sender_number] = CONVERSATION_STAGES['START']
        elif current_stage == CONVERSATION_STAGES['RECONFIRM_BOOKING']:
            if data_dict['payload']['type'] == 'list_reply':
                if sender_number in user_responses:
                    # Access the value associated with sender_number and update 'date' if it exists in the inner dictionary
                    inner_dict = user_responses[sender_number]
                    if 'time' in inner_dict:
                        inner_dict['time'] = data_dict['payload']['payload']['title']
                    else:
                        # If 'date' doesn't exist, add it to the inner dictionary
                        inner_dict['time'] = data_dict['payload']['payload']['title']

                else:
                    # If sender_number doesn't exist, create a new entry with 'date'
                    user_responses[sender_number] = {
                        'time': data_dict['payload']['payload']['title']}
                print(data_dict['payload']['payload']['title'])
                data = {
                    'channel': 'whatsapp',
                    'source': '917834811114',
                    'destination': f'{sender_number}',
                    'message': '{"type":"text","text":"Thanks for confirmation"}',
                    'src.name': 'schedulingbot',
                }

                print(user_responses)

                dynamic_date = user_responses[sender_number]['date']
                dynamic_time = user_responses[sender_number]['time']

                # Update the 'message' key in the data dictionary with the dynamic value
                data['message'] = f'{{"type":"text","text":"Appointment Rescheduled. Your appointment is schedules for: {dynamic_date} at {dynamic_time}"}}'

                # Parse the JSON message from the data dictionary
                print(data)
                response = requests.post(
                    url, data=data, headers=headers)
                values = sheet.get_all_values()
                for row_num, row_values in enumerate(values, start=1):
                    if row_values and row_values[1] == sender_number:
                        # Update the value in the 3rd column (index 2) to 'yes'
                        # Update the value in the 4th column (index 3) with the date
                        sheet.update_cell(row_num, 4, dynamic_date)
                        # Update the value in the 4th column (index 3) with the time value
                        sheet.update_cell(row_num, 5, dynamic_time)
                        print(
                            f"Updated 'yes' and date/time for mobile number {sender_number} in row {row_num}.")
                        break
                user_stage[sender_number] = CONVERSATION_STAGES['START']
                # print()



        

            
                
            
     
        # data = {
        #     'channel': 'whatsapp',
        #     'source': '917834811114',
        #     'destination': '918777714983',
        #     'message': '{"type":"list","title":"XYZ STORE","body":"Click Main Menu","globalButtons":[{"type":"text","title":"Main Menu"}],"items":[{"title":"first Section","subtitle":"first Subtitle","options":[{"type":"text","title":"Book 1","description":"Book 1 description"},{"type":"text","title":"Book 2","description":"Book 2 description"}]},{"title":"second section","subtitle":"second Subtitle","options":[{"type":"text","title":"Book 3","description":"Book 3 description"},{"type":"text","title":"Book 4","description":"Book 4 description"}]}]}',
        #     'src.name': 'schedulingbot',
        # }
        # encoded_data = urllib.parse.urlencode(data)
        # response = requests.post(url, data=encoded_data, headers=headers)
    return str(response)

if __name__ == '__main__':
    app.run(debug=True, port=8080)
