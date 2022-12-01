import json
import logging
import os.path
import re
import threading
import time
import webbrowser

from requests import Session
from werkzeug import Request
from werkzeug import Response
from werkzeug.serving import make_server
import urllib.parse as urlparse


class AuthError(RuntimeError):
    pass


CAPTURE_RESULTS = []


@Request.application
def capture(request):
    global CAPTURE_RESULTS
    data = {'redirect_url': request.url}
    data.update(request.args)
    CAPTURE_RESULTS.append(data)
    return Response('You\'re good to go!', 200)


def login():
    global CAPTURE_RESULTS
    session = Session()
    addr = urlparse.quote('http://localhost:2730', safe='')
    AZURE_ID = urlparse.quote("569fb778-44fb-4411-93cf-6a0bf7d2d157", safe='')
    AZURE_SEC = urlparse.quote("9ri8Q~O_etdiy8Xw8HHl_PXPXPO1.V6XFfxTYaAk", safe='')

    if os.path.exists('refresh.secret'):
        with open('refresh.secret') as f:
            rtoken = f.read()
        rtoken = urlparse.quote(rtoken, safe='')
        step2 = session.post("https://login.live.com/oauth20_token.srf",
                             f"client_id={AZURE_ID}&redirect_uri={addr}&client_secret={AZURE_SEC}&grant_type=refresh_token&refresh_token={rtoken}",
                             headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    else:
        print('\rStarting server (no refresh token)...'.ljust(50), end='', flush=True)
        CAPTURE_RESULTS = []
        s = make_server("localhost", 2730, capture)
        t = threading.Thread(target=s.serve_forever)
        t.start()
        webbrowser.open(
            f"https://login.live.com/oauth20_authorize.srf?client_id={AZURE_ID}&response_type=code&redirect_uri={addr}&scope=XboxLive.signin%20XboxLive.offline_access&state=")
        while len(CAPTURE_RESULTS) == 0:
            print('\rWaiting for login... (check your browser)'.ljust(50), end='', flush=True)
            time.sleep(0.1)
        code = CAPTURE_RESULTS[0]['code']
        print('\rStopping server...'.ljust(50), end='\n', flush=True)
        s.shutdown()
        t.join()

        code = urlparse.quote(code, safe='')
        step2 = session.post("https://login.live.com/oauth20_token.srf",
                             f'client_id={AZURE_ID}&client_secret={AZURE_SEC}&code={code}&grant_type=authorization_code&redirect_uri={addr}',
                             headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    # write the refresh token to a file
    with open('refresh.secret', 'w') as f:
        f.write(step2['refresh_token'])
    access_token = step2['access_token']

    # noinspection HttpUrlsUsage ffs
    step3 = session.post("https://user.auth.xboxlive.com/user/authenticate",
                         json.dumps({"Properties": {"AuthMethod": "RPS",
                                                    "SiteName": "user.auth.xboxlive.com",
                                                    "RpsTicket": f"d={access_token}"},
                                     "RelyingParty": "http://auth.xboxlive.com",
                                     "TokenType": "JWT"}),
                         headers={'Content-Type': 'application/json', 'Accept': 'application/json'}).json()

    token = step3['Token']
    user_hash = step3['DisplayClaims']['xui'][0]['uhs']

    step4 = session.post(f"https://xsts.auth.xboxlive.com/xsts/authorize",
                         json.dumps({
                             "Properties": {
                                 "SandboxId": "RETAIL",
                                 "UserTokens": [
                                     token
                                 ]
                             },
                             "RelyingParty": "rp://api.minecraftservices.com/",
                             "TokenType": "JWT"
                         }),
                         headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'x-xbl-contract-version': '1'}).json()

    xsts = step4['Token']

    # finally
    step5 = session.post("https://api.minecraftservices.com/authentication/login_with_xbox",
                         json.dumps({
                             "identityToken": f"XBL3.0 x={user_hash};{xsts}",
                             "ensureLegacyEnabled": True
                         }),
                         headers={'Content-Type': 'application/json', 'Accept': 'application/json'}).json()

    mc_access_token = step5['access_token']
    # do they own the gaming
    step6 = session.get("https://api.minecraftservices.com/minecraft/profile",
                        headers={'Authorization': f'Bearer {mc_access_token}'}).json()
    if 'error' in step6:
        raise AuthError('You don\'t own the game!')
    return mc_access_token, step6['id'], step6['name']


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    print(login())
