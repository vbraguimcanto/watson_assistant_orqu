from gevent.monkey import patch_all
patch_all()
from gevent.local import local

#from psycogreen.gevent import patch_psycopg
#patch_psycopg()

from flask import Flask, request
from flask_cors import CORS
from flask_sslify import SSLify

from ibm_watson import AssistantV2
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from urllib.parse import urlparse
from os import urandom, environ
from datetime import datetime as dt
from datetime import timedelta
import requests
import base64
import redis
import json


'''
Flask Server Configuration
'''
flask_server = Flask(__name__)
flask_server.config['SECRET_KEY'] = urandom(16)
SSLify(flask_server)
CORS(flask_server)


'''
    Facebook Webhook Configuration
'''
VERIFY_TOKEN = ""
PAGE_ACCESS_TOKEN = ""
#FB_API_URL = "https://graph.facebook.com/v6.0/me/messages?access_token={}".format(PAGE_ACCESS_TOKEN)
FB_API_URL = "https://graph.facebook.com/v6.0/me/messages"

'''
    Watson Assistant v2 Configuration
'''
iam_authenticator = IAMAuthenticator("")
watson_api = AssistantV2(version='2019-02-28', authenticator=iam_authenticator)
watson_api.set_service_url("https://gateway.watsonplatform.net/assistant/api")
ASSISTANT_ID = ""


'''
    Establish connection with Redis
'''
print("\nConnecting to IBM Cloud Redis...")
# Read Redis credentials from the `redis-credentials.json` file:
with open("redis_credentials.json") as json_file:
    redis_cred = json.load(json_file)['connection']['rediss']
connection_string = redis_cred['composed'][0]
parsed = urlparse(connection_string)
# Build the Redis root certificate .pem file:
with open("rediscert.pem", "w") as rootcert:
    coded_cert = redis_cred['certificate']['certificate_base64']
    rootcert.write(base64.b64decode(coded_cert).decode('utf-8'))
try:
    # The decode_responses flag here directs the client,
    # to convert the responses from Redis into Python 
    # strings using the default encoding utf-8.
    redis_session = redis.StrictRedis(
        host=parsed.hostname,
        port=parsed.port,
        password=parsed.password,
        ssl=True,
        ssl_ca_certs='rediscert.pem',
        decode_responses=True
    )
    print("\nConnected successfully to IBM Cloud Redis.")
except Exception as error:
    print("\nException: {}".format(error))
finally:
    pass


'''
    Bot Orch Functions
'''
def verify_fb_webhook(req):
    if req.args.get("hub.verify_token") == VERIFY_TOKEN:
        return req.args.get("hub.challenge"), 200
    else:
        return "404 Not Found", 404

def is_user_message(message):
    """Check if the message is a message from the user"""
    return (message.get('message') and
            message['message'].get('text') and
            not message['message'].get("is_echo"))

def get_watson_session(watson_api, redis_session, sender_id, assistant_id):
    # Retrieve, or set a new, Watson Assistant `session_id`.
    # Check Redis for `session_id` based on the `sender_id`:
    session_id_dt = redis_session.get(sender_id)
    if session_id_dt == None:
        # Generate a new session_id if none is present
        session_id = watson_api.create_session(assistant_id=assistant_id).get_result()['session_id']
        # Save the session_id at Redis
        redis_session.set(sender_id, "{}${}".format(session_id, dt.now().strftime("%c")))
    else:
        # Check if the present session_id is expired
        session_id_dt = session_id_dt.split('$') #Thu Jun 20 04:00:11 2019
        date_time_str = session_id_dt[1]
        date_time_obj = dt.strptime(date_time_str, '%a %b %d %H:%M:%S %Y')
        if (dt.now()-date_time_obj > timedelta(minutes=5)):
            # Generate a new session_id if the present one is expired
            session_id = watson_api.create_session(assistant_id=assistant_id).get_result()['session_id']
            # Save the new session_id at Redis
            redis_session.set(sender_id, "{}${}".format(session_id, dt.now().strftime("%c")))
        else:
            # Session at Redis is still active
            session_id = session_id_dt[0]
    return session_id


def get_watson_responses(watson_api, assistant_id, session_id, input_message):
    watson_response = watson_api.message(
        assistant_id = assistant_id,
        session_id = session_id,
        input={
            'message_type': 'text',
            'text': input_message
        }
    ).get_result()
    # Parse Watson replies
    watson_replies = []
    for x in watson_response['output']['generic']:
        # Currently, only text type messages are supported
        if x['response_type'] == 'text':
            watson_replies.append(dict(text=x['text']))
        else:
            watson_replies.append(text="ERROR: Watson Assistant is unavailable.")
    return watson_replies


def send_responses(recipient_id, watson_replies):
    response_jsons = []
    for x in watson_replies:
        """Send a response to Facebook"""
        payload = {
            'recipient': {
                'id': recipient_id
            },
            "message": x
        }
        auth = {'access_token': PAGE_ACCESS_TOKEN}
        response = requests.post(
            FB_API_URL,
            params=auth,
            json=payload
        )
        response_jsons.append(response.json())
    return response_jsons


''' 
    Flask Server Routes 
'''
@flask_server.route("/webhook", methods=['GET', 'POST'])
def listen():
    # Flask will listen at the `/webhook` endpoint.
    #print(request)
    #print("request.args['body']={}".format(request.args['body']))
    #print("request.get_data()={}".format(request.get_data()))
    if request.method == "GET":
        return verify_fb_webhook(request)

    if request.method == "POST":
        payload = request.json
        event = payload['entry'][0]['messaging']
        for x in event:
            if is_user_message(x):
                text = x['message']['text']
                sender_id = x['sender']['id']
                session_id = get_watson_session(
			watson_api=watson_api,
			redis_session=redis_session,
			sender_id=sender_id,
			assistant_id=ASSISTANT_ID
		)
                watson_replies = get_watson_responses(
			watson_api=watson_api,
			assistant_id=ASSISTANT_ID,
			session_id=session_id,
			input_message=text
		)
                print("\n\n\nRESPOSTA=\n{}\n\n\n".format(watson_replies[0]))
                send_responses(recipient_id=sender_id, watson_replies=watson_replies)
        return "200 Ok", 200

# Route for clearing completely the Redis database.
@flask_server.route('/clean_redis')
def clean_redis():
    try:
        # The decode_responses flag here directs the client,
        # to convert the responses from Redis into Python 
        # strings using the default encoding utf-8.
        iredis2 = redis.StrictRedis(
            host=parsed.hostname,
            port=parsed.port,
            password=parsed.password,
            ssl=True,
            ssl_ca_certs='rediscert.pem',
            decode_responses=True
        )
        #print("\nConnected successfully to IBM Cloud Redis.")
    except Exception as error:
        return "\nException: {}".format(error)
    finally:
        # Start clearing keys
        count = 0
        for key in iredis2.scan_iter():
            count = count + 1
            iredis2.delete(key)
        return "Deleted {} Redis keys.".format(count)


''' 
    Main 
'''
if __name__ == '__main__':
    flask_server.run(
        host="0.0.0.0", 
        port=8080, 
        debug=False
    )
