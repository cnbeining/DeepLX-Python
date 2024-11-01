import brotli
import requests
import time
import random
import json
import os
from flask import Flask, request, Response
from flask.views import MethodView
import re

PROXY = os.environ.get('PROXY', None)
TOKEN = set(os.environ.get('TOKEN', '').split(','))


app = Flask(__name__)

# Add new request validation
class TranslationRequest:
    def __init__(self, data):
        self.text = data.get('text', '')
        if isinstance(self.text, list):
            self.text = self.text[0]
        self.source_lang = data.get('source_lang', 'auto')
        self.target_lang = data.get('target_lang', 'en')
        self.tag_handling = data.get('tag_handling', None)

def verify_token(request):
    # Check query parameter
    token_param = request.args.get('token', '')
    
    # Check Authorization header
    auth_header = request.headers.get('Authorization', '')
    
    # Extract token from different Authorization header formats
    token_header = ''
    if auth_header.startswith('Bearer '):
        token_header = auth_header[7:]
    elif auth_header.startswith('DeepL-Auth-Key '):
        token_header = auth_header[15:]
    else:
        token_header = auth_header
    
    # Check if any token variant matches
    return any(token in TOKEN for token in [token_param, token_header])

class Translator(MethodView):
    def get(self):
        return {"code": 200, "msg": "Go to /translate with POST."}

    def post(self):
        if not verify_token(request):
            return Response(json.dumps({'error': 'Invalid Token'}), status=401, mimetype='application/json')
        
        # Validate request data
        try:
            req = TranslationRequest(request.json)
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=400, mimetype='application/json')
        
        translator = DeepLX(http_proxy=PROXY)
        deepl_response = translator.deepl_translate(
            req.text,
            req.source_lang,
            req.target_lang,
            tag_handling=req.tag_handling
        )
        
        if 'error' in deepl_response:
            return Response(json.dumps({'error': deepl_response['error']}), status=400, mimetype='application/json')
            
        response_body = translator.deepl_response_to_deeplx(deepl_response)
        return Response(json.dumps(response_body), mimetype='application/json')

## Helper Functions

class DeepLX(object):
    def __init__(self, http_proxy=None):
        self.url = "https://www2.deepl.com/jsonrpc?client=chrome-extension,1.28.0"
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,zh-HK;q=0.6,zh;q=0.5',
            'authorization': 'None',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'dnt': '1',
            'origin': 'chrome-extension://cofdbpoegempjloogbagkncekinflcnj',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.deepl.com/',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'none',
            'sec-gpc': '1',
            'user-agent': 'DeepLBrowserExtension/1.28.0 Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Proxy setup
        self.proxies = None
        if http_proxy:
            self.proxies = {
                'http': http_proxy,
                'https': http_proxy
            }
        self.session.proxies = self.proxies

        # Proxy
        self.http_proxy = http_proxy
        self.proxies = None
        if http_proxy:
            self.proxies = {
                'http': http_proxy,
                'https': http_proxy
            }


    @staticmethod
    def get_i_count(translate_text: str) -> int:
        return translate_text.count("i")

    @staticmethod
    def get_random_number() -> int:
        src = random.Random(time.time_ns())
        num = src.randint(8300000, 8399999)
        return num * 1000

    @staticmethod
    def get_timestamp(i_count: int) -> int:
        ts = int(time.time() * 1000)
        if i_count != 0:
            i_count = i_count + 1
            return ts - ts % i_count + i_count
        else:
            return ts

    @staticmethod
    def is_richtext(text: str) -> bool:
        """
        Check if text contains HTML-like tags
        Returns True if HTML-like tags are found, otherwise False
        """
        # Simple check for presence of HTML-like tags
        if re.search(r'<[^>]+>', text):
            return True
        return False

    @staticmethod
    def format_post_string(post_data: dict) -> str:
        """Format the JSON string with specific spacing rules for the 'method' field"""
        post_str = json.dumps(post_data, ensure_ascii=False)
        
        if (post_data["id"] + 5) % 29 == 0 or (post_data["id"] + 3) % 13 == 0:
            post_str = post_str.replace('"method":"', '"method" : "', 1)
        else:
            post_str = post_str.replace('"method":"', '"method": "', 1)
        
        return post_str

    def make_deepl_request(self, post_str: str,
                           url_method: str = "LMT_handle_jobs") -> dict:
        """
        Make HTTP request to DeepL API and handle the response
        Returns JSON response or error dictionary
        """
        url = f"{self.url}?client=chrome-extension,1.28.0&method={url_method}"

        try:
            response = self.session.post(
                url,
                post_str,
            )
            
            if not response.ok:
                return {'error': response.text}
                
            try:
                return response.json()
            except Exception:
                return json.loads(brotli.decompress(response.content))
                
        except Exception as e:
            return {'error': str(e)}


    @staticmethod
    def deepl_response_to_deeplx(data):
        alternatives = []
        if 'result' in data and 'translations' in data['result'] and len(data['result']['translations']) > 0:
            num_beams = len(data['result']['translations'][0]['beams'])
            for i in range(num_beams):
                alternative_str = ""
                for translation in data['result']['translations']:
                    if i < len(translation['beams']):  # Check if beam index exists
                        alternative_str += translation['beams'][i]['sentences'][0]['text']
                alternatives.append(alternative_str)
        return {
            "alternatives": alternatives,
            "code": 200,
            "data": " ".join(translation['beams'][0]['sentences'][0]['text'] for translation in data['result']['translations']),
            "id": data['id'],
            "method": "Free", 
            "source_lang": data['result']['source_lang'],
            "target_lang": data['result']['target_lang']
        }

    ## Translate Functions

    def deepl_split_text(self, text: str, tag_handling: bool = None) -> dict:
        source_lang = 'auto'
        # Set text_type to richtext if tag_handling is True, otherwise use detection
        text_type = 'richtext' if (tag_handling or self.is_richtext(text)) else 'plaintext'
        post_data = {
            "jsonrpc": "2.0",
            "method": "LMT_split_text",
            "params": {
                "commonJobParams": {
                    "mode": "translate"
                },
                "lang": {
                    "lang_user_selected": source_lang
                },
                "texts": [text],
                "textType": text_type
            },
            "id": self.get_random_number()
        }
        post_str = self.format_post_string(post_data)
        return self.make_deepl_request(post_str, url_method="LMT_split_text")


    def deepl_translate(self, text, source_lang='auto', target_lang='en', preferred_num_beams=4, tag_handling=None):
        if not text:
            return {'error': 'No text to translate'}
            
        split_result = self.deepl_split_text(text, tag_handling)
        if 'error' in split_result:
            return split_result
        # Set source_lang to detected language from split_result unless explicitly specified
        if source_lang == 'auto':
            source_lang = split_result['result']['lang']['detected'].lower()
        i_count = self.get_i_count(text)
        # Build jobs array from split text chunks
        jobs = []
        chunks = split_result['result']['texts'][0]['chunks']
        for idx, chunk in enumerate(chunks):
            sentence = chunk['sentences'][0]
            # Calculate context windows
            context_before = []
            context_after = []
            
            if idx > 0:
                context_before = [chunks[idx-1]['sentences'][0]['text']]
            if idx < len(chunks) - 1:
                context_after = [chunks[idx+1]['sentences'][0]['text']]
                
            jobs.append({
                "kind": "default",
                "preferred_num_beams": preferred_num_beams,
                "raw_en_context_before": context_before,
                "raw_en_context_after": context_after,
                "sentences": [{
                    "prefix": sentence['prefix'],
                    "text": sentence['text'],
                    "id": idx + 1
                }]
            })
        post_data = {
            "jsonrpc": "2.0",
            "method": "LMT_handle_jobs",
            "id": self.get_random_number(),
            "params": {
                "commonJobParams": {
                    "mode": "translate"
                },
                "lang": {
                    "source_lang_computed": source_lang.upper(),
                    "target_lang": target_lang.upper()
                },
                "jobs": jobs,
                "priority": 1,
                "timestamp": self.get_timestamp(i_count)
            }
        }
        post_str = self.format_post_string(post_data)
        return self.make_deepl_request(post_str, url_method="LMT_handle_jobs")

# Register routes
app.add_url_rule('/', view_func=Translator.as_view('root'))
app.add_url_rule('/translate', view_func=Translator.as_view('translate'))

if __name__ == "__main__":
    app.run()

