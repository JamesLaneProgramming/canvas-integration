from __future__ import print_function
from __future__ import unicode_literals
'''
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
'''
#TODO: Setup workflow for OAuth2 refresh tokens

import os, sys
from os import environ
import sys
import requests
import json
import hashlib
from functools import wraps
from flask import Flask, flash, render_template, request, abort, redirect, url_for, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mongoengine import MongoEngine
#Should not import canvas_API_request function. Instead create an endpoint for specific action.
from canvas_module import update_canvas_email, create_canvas_login
from canvas_module import enroll_canvas_student, extract_rubric_data, search_students
from users.user_model import User
from assessments.assessment_model import Criterion
from learning_outcomes.learning_outcome_model import Learning_Outcome
from subjects.subject_model import Subject

#Set the default folder for templates
application = Flask(__name__, template_folder='templates')

#Set application secret key to secure against CSRF
application.secret_key = 'super secret key'
application.config['SESSION_TYPE'] = 'filesystem'

#Configure mongodb server connection
application.config['MONGODB_SETTINGS'] = {
    'db': 'canvas_integration',
    'host': 'ds125684.mlab.com:25684',
    'username': 'James',
    'password': environ.get('mongoDB_Password'),
    'authentication_source': 'canvas_integration'
}

#Initialise the mongo engine.
db = MongoEngine(application)

#Configure flask-login
login_manager = LoginManager()
login_manager.session_protection = 'strong'

#Redirect to login view when a user has yet to authenticate.
login_manager.login_view = 'login'
login_manager.init_app(application)

#user_loader callback used to load a user from a session ID.
@login_manager.user_loader
def load_user(user_id):
    return User.objects(pk=user_id).first()

def main():
    application.debug = True
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port)

@application.route('/')
def home():
    return render_template('home.html')

@application.route('/signup', methods=['GET', 'POST'])
def signup():
    if(request.method == 'POST'):
        username = request.form['username']
        password = request.form['password']
        assert username is not None
        assert password is not None
        User.create(username, password)
        return redirect('/')
    else:
        return render_template('signup.html')

def require_hubspot_signature_validation(func):
    #https://developers.hubspot.com/docs/faq/validating-requests-from-hubspot
    #https://developers.hubspot.com/docs/methods/webhooks/webhooks-overview
    @wraps(func)
    def validate_hubspot_response_signature(*args, **kwargs):
        hubspot_client_secret = environ.get('hubspot_client_secret')
        hubspot_request_signature = request.headers.get('X-HubSpot-Signature')
        request_method = request.method
        request_uri = request.base_url
        request_body = request.get_data(as_text=True)
        
        print('client_secret: ', type(hubspot_client_secret))
        print('request_method: ', type(request_method))
        print('request_uri: ', type(request_uri))
        print('request_body: ', type(request_body))

        hash_string = hubspot_client_secret + request_method + request_uri+ request_body

        request_signature = hashlib.sha256(hash_string.encode('utf-8'))
        print('hash_string, ', hash_string)
        print(hubspot_request_signature)
        print(request_signature.hexdigest())
        if(hubspot_request_signature == request_signature.hexdigest()):
            return func(*args, **kwargs)
        else:
            print('Unauthenticated')
            return func(*args, **kwargs)
    return validate_hubspot_response_signature

@application.route('/login', methods=['GET','POST'])
def login():
    if(request.method == 'POST'):
        username = request.form['username']
        password = request.form['password']
        assert username is not None
        assert password is not None
        user = User.authenticate(username, password)
        if(user != None and user.is_authenticated):
            login_status = login_user(user)
            flash('Logged in successfully.')
            #TODO: Issue redirecting to /None after successful login
            next = request.args.get('next')
            # is_safe_url should check if the url is safe for redirects.
            # See http://flask.pocoo.org/snippets/62/ for an example.
            return redirect(next)
        else:
            return redirect('login', code=302)
    else:
        return render_template('login.html')

@application.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

@application.route('/hubspot')
@login_required
def authenticate_hubspot():
    '''
    Hubspot OAuth workflow:

    Direct users to https://app.hubspot.com/oauth/authorize with the following
    query parameters:
        -client_id
        -scope
        -redirect_uri

    They will be prompted to authenticate and authorise the application.

    Users will be redirected to the redirect_uri with a code query parameter.
    
    Use the code above to request access token and refresh token.
    Headers = Content-Type: application/x-www-form-urlencoded;charset=utf-8
    Data:
        -grant_type=authorisation_code
        -client_id
        -client_secret
        -redirect_uri
        -code
    POST https://app.hubspot.com/oauth/v1/token
    '''
    try:
        client_id = environ.get('hubspot_client_id')
        scope = environ.get('hubspot_scopes')
        redirect_uri = url_for('request_refresh_token', _external=True,
                               _scheme='https')
    except Exception as error:
        raise error
    return redirect('https://app.hubspot.com/oauth/authorize?client_id={0}&scope={1}&redirect_uri={2}'.format(client_id,
                                                                                                  scope,
                                                                                                  redirect_uri))
@application.route('/hubspot/request_refresh_token')
@login_required
def request_refresh_token():
    try:
        code = request.args.get('code')
        client_id = environ.get('hubspot_client_id')
        client_secret = environ.get('hubspot_client_secret')
        '''
        redirect_uri must match the redirect_uri used to intitiate the OAuth
        connection

        '''
        redirect_uri = url_for('request_refresh_token', _external=True,
                               _scheme='https')
    except Exception as error:
        raise error

    _headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'
               }
    data = {
            'grant_type':'authorization_code', 
            'client_id': client_id,
            'client_secret': client_secret, 
            'redirect_uri': redirect_uri,
            'code': code
           }

    try:
        post_request = requests.post(
                                     'https://api.hubapi.com/oauth/v1/token',
                                     headers=_headers, 
                                     data=data
                                    )
        access_token = post_request.json()['access_token']
        refresh_token = post_request.json()['refresh_token']
    except Exception as error:
        raise error

    response = make_response()
    response.set_cookie('hubspot_access_token', access_token)
    User.set_refresh_token(current_user.id, refresh_token)
    return response

@application.route('/hubspot/refresh_access_token', methods=['GET'])
@login_required
def refresh_access_token():
    try:
        refresh_token = current_user.refresh_token
    except Exception as error:
        raise error

    #Request.

@application.route('/hubspot/workflows', methods=['GET'])
@login_required
def workflows():
    try:
        access_token = request.cookies.get('hubspot_access_token')
    except Exception as error:
        return redirect(url_for('authenticate_hubspot'))

    endpoint = 'https://api.hubapi.com/automation/v3/workflows'
    request_headers = {
                       "Content-Type": "application/json",
                       "Authorization": "Bearer " + str(access_token)
                      }
    try:
        get_request = requests.get(endpoint, headers=request_headers)
        return get_request.json()
    except Exception as error:
        raise error

@application.route('/hubspot/workflow_history/<workflow_id>')
@login_required
def workflow_history(workflow_id):
    try:
        access_token = request.cookies.get('hubspot_access_token')
    except Exception as error:
        return redirect(url_for('authenticate_hubspot'))
    
    domain = 'https://api.hubapi.com'
    endpoint = '/automation/v3/logevents/workflows/{0}/filter'
    request_url = domain + endpoint.format(workflow_id)
    request_headers = {
                       "Content-Type": "application/json",
                       "Authorization": "Bearer " + str(access_token)
                      }
    request_parameters = {
                          "types": ["ENROLLED"]
                         }
    try:
        put_request = requests.put(
                             request_url, 
                             headers=request_headers,
                             params=request_parameters
                            )
        if put_request.status_code == 401:
            return redirect(url_for('authenticate_hubspot'))
        else:
            return put_request.text
    except Exception as error:
        raise error
    
@application.route('/rubric_data')
@login_required
def rubric_data():
    course_ID = 144
    assessment_ID = 667
    request = extract_rubric_data(course_ID, assessment_ID)
    map_rubric_data(request.json())
    print(Rubric_Assessment.objects().first())
    return request.text

@application.route('/subjects', methods=['GET', 'POST'])
@login_required
def subjects():
    if(request.method == 'GET'):
        subjects = Subject.read()
        learning_outcomes = json.loads(Learning_Outcome.read())
        return render_template('subjects.html',
                               subjects=subjects,
                               learning_outcomes=learning_outcomes)
    elif(request.method == 'POST'):
        try:
            subject_code = request.form['subject_code_field']
            subject_name = request.form['subject_name_field']
            subject_description = request.form['subject_description_field']
            learning_outcome_ids = request.form.getlist('subject_learning_outcomes_field[]')
        except Exception as error:
            raise error

        subject_learning_outcomes = []
        for each_learning_outcome_id in learning_outcome_ids:
            subject_learning_outcomes.append(Learning_Outcome.index(each_learning_outcome_id))

        subject = Subject(
                          subject_code,
                          subject_name, 
                          subject_description,
                          subject_learning_outcomes
                         ).save()
        return subject.to_json()

@application.route('/learning_outcomes', methods=['GET', 'POST'])
@login_required
def learning_outcomes():
    if(request.method == 'GET'):
        learning_outcomes = json.loads(Learning_Outcome.read())
        return render_template('learning_outcomes.html', 
                               learning_outcomes=learning_outcomes)
    elif(request.method == 'POST'):
        try:
            learning_outcome_name = request.form['learning_outcome_name_field']
            learning_outcome_description = request.form['learning_outcome_description_field']
        except Exception as error:
            raise error
        try:
            learning_outcome = Learning_Outcome(
                             learning_outcome_name,
                             learning_outcome_description
                            )
            learning_outcome.save()
            return "success"
        except Exception as error:
            return abort(500)

@application.route('/criterion', methods=['GET', 'POST'])
@login_required
def criterion():
    if(request.method == 'GET'):
        criterion = json.loads(Criterion.read())
        learning_outcomes = json.loads(Learning_Outcome.read())
        return render_template('criterion.html',
                              criterion=criterion,
                              learning_outcomes=learning_outcomes)
    elif(request.method == 'POST'):
        try:
            criterion_name = request.form['criterion_name_field']
            criterion_description = request.form['criterion_description_field']
            criterion_points = request.form['criterion_points_field']
            criterion_learning_outcomes = request.form.getlist('criterion_learning_outcomes_field[]')
        except Exception as error:
            raise error

        try:
            criterion = Criterion(criterion_name=criterion_name,
                                  criterion_description=criterion_description,
                                  criterion_points=criterion_points,
                                  criterion_learning_outcomes=criterion_learning_outcomes).save()
            return "Success"
        except Exception as error:
            raise error

@application.route('/assessments', methods=['GET', 'POST'])
@login_required
def assessments():
    if(request.method == 'GET'):
        assessments = json.loads(Assessment.read())
        return render_template('assessments.html', 
                               assessments = assessments)

def map_rubric_data(submission_data):
    for each_submission_item in submission_data:
        try:
            submission_ID = each_submission_item['id']
            submission_assignment_ID = each_submission_item['assignment_id']
        except Exception as error:
            raise error
        try:
            submission_rubric_assessment = each_submission_item['rubric_assessment'] 
        except Exception as error:
            pass
        if(submission_rubric_assessment):
            submission = submission_object(submission_ID, submission_assignment_ID,
                                          submission_rubric_assessment)
            submission_grades = []
            for each_criteria in submission.criteria:
                try:
                    learning_outcome = Learning_Outcome(int(each_criteria.id),
                                                        float(each_criteria.points)).save()
                except Exception as error:
                    #Some points are marked blank and cannot be converted. 
                    pass
                submission_grades.append(learning_outcome)
            assessment = Rubric_Assessment.create(each_submission_item['user_id'], 
                                                  Assessment.objects(assessment_id=667),
                                                  submission_grades)
            learning_outcome_count = 0
            grade_total = 0
            for each_learning_outcome in assessment.grades:
                learning_outcome_count = learning_outcome_count + 1
                grade_total = grade_total + 1
                if(grade_total == 21):
                    print(grade_total)
                if(grade_total == 36):
                    print(grade_total)

class submission_object():
    def __init__(self, submission_ID, submission_assessment_ID,
                 submission_rubric_assessment):
        self.criteria = []
        self.id = submission_ID
        self.assessment_ID = submission_assessment_ID
        for key, value in submission_rubric_assessment.items():
            points = None
            comments = None
            try:
                points = value['points']
                comments = value['comments']
            except KeyError as error:
                pass
            except Exception as error:
                raise error
            if(points != None):
                criterion_object = criterion(key, points, comments)
                self.criteria.append(criterion_object)

@application.route('/students', methods=['GET', 'POST'])
@login_required
def student_search():
    if(request.method == 'POST'):
        try:
            search_term = request.form['search_term']
            search_results = search_students(search_term)
            #TODO: Replace this with request.json() for encoding purposes
            return search_results.text
        except Exception as error:
            raise error
    else:
        return render_template('student_search.html')

@application.route('/create-account', methods=['POST'])
#@require_hubspot_signature_validation
def create_canvas_account():
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
    Note: A course ID will be sent from the webhook as a query paramter. Is this safe?
    '''
    try:
        '''
        Must save query parameter before conversion as int() cannot handle
        None
        '''
        course_ID = request.args.get('course_id')
        section_ID = request.args.get('section_id')
        try:
            course_ID = int(course_ID)
            section_ID = int(section_ID)
        except Exception as error:
            print('Could not convert course/section ids to int')
            raise error
    except Exception as error:
        raise error
    
    #Validate POST payload
    if not request.json:
        return abort(415)
    else:
        json_data = request.get_json()
        try:
            first_name = json_data['properties']['firstname']['value']
            last_name = json_data['properties']['lastname']['value'] 
            student_email = json_data['properties']['email']['value']
        except KeyError as error:
            print("Could not extract json fields")
            return abort(415)
        except Exception as error:
            print(error)

    student_name = first_name + " " + last_name
    #TODO YOU NEED TO CHECK IF THE USER ALREADY EXISTS
    creation_response = create_canvas_login(student_name, student_email)
    if(creation_response.status_code == 400):
        print("The user already exists")
        students_found = json.loads(search_students(student_email).text)
        for each_student in students_found:
            #Need to implement code for response containing array of users.
            existing_user_id = each_student['id']
            enrollment_response = enroll_canvas_student(existing_user_id, course_ID)
            if(enrollment_response.status_code == 200):
                return enrollment_response
            else:
                return enrollment_response.status_code

    elif(creation_response.status_code == 200):
        try:
            student_details = json.loads(creation_response.text)
            try:
                student_ID = int(student_details['id'])
            except TypeError as error:
                print("Webhook is most likely sending array of student data.")
            except Exception as error:
                raise error
            enrollment_response = enroll_canvas_student(student_ID, course_ID, section_ID)
            print(enrollment_response.text)
        except Exception as error:
            raise error
        '''
        TODO You will need to query the canvas Users endpoint with the search_term query parameter to find the user and return ID.
        This ID will be used to enroll the student in selected course if their
        account already exists
        '''
        return str(enrollment_response.status_code)
    '''
    user_data = post_request.get_json()
    #enroll_post_request = enroll_canvas_student(create_post_request)
    if (post_request.status_code == 201):
        application.logger.info(post_request)
        return render_template('Canvas_Account_Creation_Successful.html'), 201
    else:
        application.logger.info(post_request)
        return "Canvas account could not be created at this time...\
                Please try again later or contact us for more information"
    '''

#Opens the YAML file at the specified directory and returns the scriptable YAML object.
def get_config(_dir):
    '''
    Arguments
    ---------
    _dir(String):
        Takes a directory method argument used to load configuration.
    Returns
    -------
    file_content:
        Reads the file specified by the _dir string and returns the contents
        using yaml.load(). Alternatively you could use yaml.safe_load().
    '''
    
    file_content = None

    #Checks whether the _dir method argument is a string. isinstance() supports DataTypes that inherit the String base class.
    assert isinstance(_dir, str)
    
    #Check if the directory method argument exists in the current filesystem.
    if os.path.exists(_dir):
        with open(_dir, 'r') as config_file:
            try:
                print('config accessed and read')
                #Load the configuration into a scriptable object.
                file_content = yaml.load(config_file)
            except IOError as error:
                raise error
                sys.exit(0)
            except EOFError as error:
                raise error
                sys.exit(0)
            except ImportError as error:
                print("YAML module could not be imported, please ensure that YAML module has been installed and is in the requirements.txt file")
            except Exception as error:
                raise error
            if(file_content != None):
                return file_content
            else:
                print("Could not load configuration from file but no errors were thrown")
    else:
        print('_dir method argument is not a valid directory in the current filesystem')

def google_request(spreadsheet_ID, range_name, scope):
    '''
    Arguments
    ---------
    spreadsheet_ID(String):
        Takes a string agrument that represents the google spreadsheet
        identifier.
    range_name(String):
        Take a string argument that represents the google sheet ranges to
        retreive data from. Format for the string is as follows:
            '<sheet_name>!<start_range>:<end_range>'
    scope(Google)
    '''
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', scope)
        creds = tools.run_flow(flow, store)
    service = build('sheets', 'v4', http=creds.authorize(Http()))

    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_ID,
                                                range=range_name).execute()
    sheet_data = result.get('values', [])
    
    if not sheet_data:
        sys.exit()
    else:
        return sheet_data

if __name__ == "__main__":
    main()
