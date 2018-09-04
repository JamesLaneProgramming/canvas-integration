#!usr/bin/python
from __future__ import print_function
#Google OATH imports
try:
    from googleapiclient.discovery import build
    from httplib2 import Http
    from oauth2client import file, client, tools
except Exception as error:
    print('Please run the following command to install Google API modules:',
          '\n')
    print('pip3 install --upgrade google-api-python-client oauth2client')
    raise error
#End Google module imports

import os
from os import environ
import yaml
import sys
from functools import reduce
import requests
import json
from flask import Flask, render_template, request, abort
import argparse

environment = None
application = Flask(__name__, template_folder='templates')

parser = argparse.ArgumentParser(description='Command line arguments')
parser.add_argument('-env', 
                    '--environment',
                    help='Sets the environment for the program.')
args = parser.parse_args()
@application.route('/')
def home():
    return render_template('home.html')

@application.route('/create-account', methods=['POST'])
def create_account():
    '''
    Docstring
    ---------
    create_account() should only be run in a production environment
    Arguments
    ---------
    student_data(JSON Object):
        Takes a JSON Object that contains firstname, lastname and email
    Returns
    -------
    Account_Creation_Successful(template):
        Returns a template to be rendered by Flask on successful request.
    '''

    #Attempts to lead canvas_secret from environment
    try:
        _headers = environ.get('canvas_secret')
    except KeyError as error:
        '''
        If canvas_secret token cannot be loaded from the server, return a 500
        internal server error
        '''
        abort(500)
    #Attempts to load json data from student_data
    
    if not request.json:
        abort(415)
    else:
        json_data = request.get_json()
        try:
            first_name = json_data['properties']['firstname']['value']
            last_name = json_data['properties']['lastname']['value'] 
            student_email = json_data['properties']['email']['value']
        except KeyError as error:
            abort(415)
    student_name = first_name + " " + last_name
    post_request = create_canvas_login(student_name, student_email,
                                           _headers)
    user_data = post_request.get_json()
    #enroll_post_request = enroll_canvas_student(create_post_request)
    if (post_request.status_code == 201):
        app.logger.info(post_request)
        return render_template('Canvas_Account_Creation_Successful.html'), 201
    else:
        app.logger.info(post_request)
        return "Canvas account could not be created at this time...\
                Please try again later or contact us for more information"

def parse_arguments():
    global environment
    environment = args.environment.upper()
    if (environment == None):
        print("environment could not be parsed, exiting.")
        sys.exit(0)
def main():
    #Handle arguments parsed from the command line
    parse_arguments()
    if environment == 'DEVELOPMENT':
        app.logger.info("Starting development build")
        config = get_config('./config.yaml')

        #Canvas config variables
        try:
            request_parameters = config['canvas']['request_parameters']
            course_ID = config['canvas']['course_ID']
            canvas_bearer_token = config['canvas']['bearer_token']
        except KeyError as error:
            print('Could not find config key specified')
            raise error

        #Google sheets config variables
        try:
            spreadsheet_ID = config['google_sheets']['spreadsheet_ID']
            range_name = config['google_sheets']['sheet_range']
            scope = config['google_sheets']['scope']
        except KeyError as error:
            print('could not find config key specified')
            raise error
    elif environment == 'PRODUCTION':
        app.logger.info('Starting production server')
        #Retrieve config variables from Heroku
        #config_variable = environ.get('')
        application.debug = True
        port = int(os.environ.get('PORT', 5000))
        application.run(host='0.0.0.0', port=port)
    else:
        print('Environment parsed but does not match')
        print('Posible environments are: development/production/testing')

    #sheet_data = google_request(spreadsheet_ID, range_name, scope)
    #canvas_data = canvas_request(canvas_bearer_token, course_ID,
    #                             request_parameters)
    #update_canvas_emails(sheet_data, canvas_data, canvas_bearer_token)

#Opens the YAML file at the specified directory and returns the YAML object.
def get_config(_dir):
    if os.path.exists(_dir):
        with open(_dir, 'r') as config_file:
            try:
                print('Token file accessed and read')
                file_content = yaml.load(config_file)
            except IOError as error:
                raise error
                sys.exit()
            except EOFError as error:
                raise error
                sys.exit()
    else:
        print('Could not find config file')
        sys.exit()
    return file_content

def google_request(spreadsheet_ID, range_name, scope):
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', scope)
        creds = tools.run_flow(flow, store)
    service = build('sheets', 'v4', http=creds.authorize(Http()))

    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_ID,
                                                range=range_name).execute()
    sheet_data = result.get('values', [])
    
    #Check if the sheet_data is empty
    if not sheet_data:
        print("No values found in spreadsheet, Exiting")
        sys.exit()
    else:
        return sheet_data

def canvas_request(canvas_bearer_token, course_ID, request_parameters=''):
    '''
    Docstring
    '''
    headers = {'Authorization' : 'Bearer {0}'.format(canvas_bearer_token)}
    url = 'https://coderacademy.instructure.com/api/v1/courses/{0}/users?{1}'.format(course_ID,
                                                                              request_parameters)
    response = requests.get(url, headers=headers)
    if not response:
        print(response)
        print("No data found at endpoint: {0}".format(url))
        sys.exit()
    else:
        #Load the request data into a JSON object
        canvas_data = json.loads(response.text)
        return canvas_data

def update_canvas_emails(sheet_data, canvas_data, _headers):
    #Lambda to get student name from canvas for matching
    canvas_name_lambda = lambda x: x['name']
    #Lambda to get student ID from canvas to update email with
    canvas_ID_lambda = lambda x: x['id']
    #Lambda to get student name from sheets for matching
    sheet_name_lambda = lambda y: y[0]
    #Lambda to get student email from sheets to update canvas with
    sheet_email_lambda = lambda z: z[2]

    #Update emails based on canvas_data['id'] and sheet_data['email']
    for each_sheet_student in sheet_data:
        for each_canvas_student in canvas_data:
            #Use variables to compare
            student_sheet_name = sheet_name_lambda(each_sheet_student)
            student_canvas_name = canvas_name_lambda(each_canvas_student)
            
            #Use variables to update
            student_sheet_email = sheet_email_lambda(each_sheet_student)
            student_canvas_ID = canvas_ID_lambda(each_canvas_student)
            
            if student_canvas_name == student_sheet_name:
                update_canvas_email(
                                    student_canvas_ID,
                                    student_sheet_email,
                                    _headers
                                   )


def enroll_canvas_student(student_ID, course_ID, _headers):
    _headers = {'Authorization' : 'Bearer {0}'.format(_headers)}
    parameters = {'enrollment[user_id]': student_id}
    url = 'https://coderacademy.instructure.com/api/v1/courses/{0}/enrollments'.format(course_ID)
    post_request = requests.post(url, headers = _headers, data = parameters)
    return post_request

def create_canvas_login(student_name, student_email, _headers):
    _headers = {'Authorization' : 'Bearer {0}'.format(_headers)}
    parameters = {'user[name]':student_name, 'pseudonym[unique_id]':student_email}
    url = 'https://coderacademy.instructure.com/api/v1/accounts/1/users'
    post_request = requests.post(url, headers = _headers, data = parameters)
    return post_request

def update_canvas_email(student_ID, email, _headers):
    _headers = {'Authorization' : 'Bearer {0}'.format(_headers)}
    parameters = {'user[email]':email}
    url = 'https://coderacademy.instructure.com/api/v1/users/{0}.json'.format(student_ID)
    update_request = requests.put(url, headers = _headers, data = parameters)

    #Condition if request successful
    if(update_request.status_code == 200):
        print("Successfully updated canvas email")
    elif(update_request.status_code == 422):
        print("Error: ", update_request.status_code)
    else:
        print("There was an error updating a canvas email", '\n')
        print("Student with ID: {0} failed to update with error code: {1}".format(
                                                                                  student_ID, 
                                                                                  update_request.status_code
                                                                                 ))
if __name__ == "__main__":
    main()
