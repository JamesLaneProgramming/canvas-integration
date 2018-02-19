#!usr/bin/python

import sys
import requests
import json

def main():
    headers = {'Authorization' : 'Bearer 9870~whgKFoccltWnzegnHNscC9Z6ZBmJfhBt3Zu6Qu22inaf46JXpantxSEkakmvOgWZ'}
    response = requests.get('https://coderacademy.instructure.com/api/v1/courses/92/users?per_page=100',
                headers=headers)

    #Convert response into string
    responseText = response.text
    #Remove JSON array symbols
    responseText = responseText[1:]
    responseText = responseText[:-2]
    #Split JSON data for iteration purposes
    responseText = responseText.split("},")
    '''
    Note: 
    Splitting the string in this way will remove the REGEX expression from the
    responseText and will need to be added manually later while iterating.
    Removing the comma will also convert the response text into an array of
    strings rather than an array of JSON data.
    '''

    for each_element in responseText:
        #Append the JSON data so that we can parse it into a dictionary
        each_element += "}"

        #Load the JSON data into a dictionary so that we can read key/value pairs
        jsondata = json.loads(each_element)

        #Iterate through the dictionary and find login_id.
        for key, value in jsondata.items():
            if(key == 'login_id'):
                print(value)

if __name__ == "__main__":
    main()

