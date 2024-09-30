#© 2024 Daniel DeMoney. All rights reserved.
'''
UNUSED FILE>>>>MOVED TO DATABASE SERVER

'''

'''
Exectution flow

signup.html

auth.js

auth_server.py
'''

from flask_bcrypt import Bcrypt
import json
from flask import Flask, request, jsonify, abort, Response
import jwt
from google.oauth2 import id_token
from google.auth.transport import requests
import os
from auth_logic import get_token
from typing import Dict
from user_table import UserTable
from user import User
import uuid
from uuid import UUID
from user import UserInvalidData
from helper_functions import HelperFunctions
import sys
import daemon
from flask_cors import CORS
from user_preferences_table import UserPreferencesTable
from user_location_table import UserLocationTable

app : Flask = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)
API_KEY : str = os.environ["GOOGLE_API_KEY"]
PORT : int = 5007
class AuthServer():
    #UNUSED
    def shutdown():
        print("Handling auth server shutdown")
        HelperFunctions.handle_sigterm("auth_server")
        print("Shutdown successful")
    def run():
        print("Running server")
        try:
            app.run(debug=False, port=PORT)
        except:
            AuthServer.shutdown()

if __name__ == '__main__':
    HelperFunctions.write_pid_to_temp_file("auth_server")
    AuthServer.run()

    #Unused code, simpler code for dev
    '''
    try:
        # Check for the -I argument
        if '-i' in sys.argv:
            # Run the script normally without daemonizing
            print("Running in non-daemon mode")
            app.run(debug=False, port=PORT)
        else:
            print("Starting daemon")
            log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs'))
            temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'temp'))
            stdout_path = os.path.join(log_dir, 'auth_server.stdout')
            stderr_path = os.path.join(log_dir, 'auth_server.stderr')
            pid_path = os.path.join(temp_dir, 'auth_server_pid')
            daemon = AuthServer(pid_path, stderr_path, stdout_path)
            daemon.start()
    except Exception as e:
        print(e)
        raise e
    '''
