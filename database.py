import json

class DataStore():
    def __init__(self):
        with open('data.json', 'r') as fp:
            self.data = json.load(fp)
        
    def get_room_types(self):
        return self.data['rooms']

    def add_booking(self, name, check_in_date, check_out_date, room_type,duration, amount,  aadhaar, number):
        new_booking = {
            "Name": name,
            "Phone Number": number,
            "Aadhaar": aadhaar,
            "Room": room_type,
            "Check-in date": check_in_date,
            "Check-out date": check_out_date,
            "Duration": duration,
            "Amount": amount
        }

        self.data['bookings'].append(new_booking)

        with open('data.json', 'w') as fp:
            json.dump(self.data, fp)       

    # def get_empty_rooms(self, check_in_date, check_out_date, room_type):
    #     total = self.data['rooms'][room_type]
    #     for booking in self.data['bookings']:
    #         if booking['Room'] == room_type:
    #             if booking['Check-in-date'] >= check_in_date and booking['Check-in-date'] <= check_out_date:
    #                 total -=1
    #             elif booking['Check-out-date'] >= check_in_date and booking['Check-out-date'] <= check_out_date:
    #                 total -=1

    #     return total
    