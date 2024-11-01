import re
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List, Union
import brotli
import httpx
import time
import random
import json
import os
from pydantic import BaseModel

"""
FastAPI application that provides a DeepL translation API wrapper.
This service allows for text translation using DeepL's service without requiring an official API key.
"""

PROXY = os.environ.get('PROXY', None)
TOKEN = set(os.environ.get('TOKEN', '').split(','))

# Define request/response models
class TranslationRequest(BaseModel):
    """
    Pydantic model for translation request parameters.
    
    Attributes:
        text (Union[str, List[str]]): Text to translate
        source_lang (str): Source language code (default: 'auto')
        target_lang (str): Target language code (default: 'en')
        tag_handling (str): Optional HTML tag handling parameter
    """
    text: str | List[str]
    source_lang: Optional[str] = 'auto'
    target_lang: Optional[str] = 'en'
    tag_handling: Optional[str] = None

class TranslationResponse(BaseModel):
    """
    Pydantic model for translation response.
    
    Attributes:
        alternatives (List[str]): List of alternative translations
        code (int): Response status code
        data (str): Main translation result
        id (int): Translation request ID
        method (str): Translation method used
        source_lang (str): Detected or specified source language
        target_lang (str): Target language
    """
    alternatives: List[str]
    code: int
    data: str
    id: int
    method: str
    source_lang: str
    target_lang: str

app = FastAPI()

# Token verification dependency
async def verify_token(request: Request) -> bool:
    """
    Dependency function to verify API token from request.
    
    Args:
        request (Request): FastAPI request object
    
    Returns:
        bool: True if token is valid
        
    Raises:
        HTTPException: If token is invalid
    """
    # Check query parameter
    token_param = request.query_params.get('token', '')
    
    # Check Authorization header
    auth_header = request.headers.get('Authorization', '')
    
    # Extract token from different Authorization header formats
    token_header = ''
    if auth_header.startswith('Bearer '):
        token_header = auth_header[7:]  # Remove 'Bearer ' prefix
    elif auth_header.startswith('DeepL-Auth-Key '):
        token_header = auth_header[15:]  # Remove 'DeepL-Auth-Key ' prefix
    else:
        token_header = auth_header  # Use raw header value
    
    # Check if any token variant matches
    if any(token in TOKEN for token in [token_param, token_header]):
        return True
        
    raise HTTPException(status_code=401, detail="Invalid Token")

class DeepLX:
    """
    DeepL translation client that interfaces with DeepL's web API.
    Provides methods for text splitting and translation without requiring an official API key.
    """
    
    def __init__(self, http_proxy=None):
        """
        Initialize DeepLX client.
        
        Args:
            http_proxy (str, optional): HTTP proxy URL
        """
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
        
        self.client = httpx.AsyncClient(
            headers=self.headers,
            proxy=http_proxy,
        )


    @staticmethod
    def get_i_count(translate_text: str) -> int:
        """Count occurrences of 'i' in text for timestamp calculation."""
        return translate_text.count("i")

    @staticmethod
    def get_random_number() -> int:
        """Generate random request ID within DeepL's expected range."""
        src = random.Random(time.time_ns())
        num = src.randint(8300000, 8399999)
        return num * 1000

    @staticmethod
    def get_timestamp(i_count: int) -> int:
        """
        Generate timestamp for request based on 'i' count.
        
        Args:
            i_count (int): Number of 'i' characters in text
            
        Returns:
            int: Calculated timestamp
        """
        ts = int(time.time() * 1000)
        if i_count != 0:
            i_count = i_count + 1
            return ts - ts % i_count + i_count
        else:
            return ts

    @staticmethod
    def is_richtext(text: str) -> bool:
        """Check if text contains HTML-like tags"""
        return bool(re.search(r'<[^>]+>', text))

    @staticmethod
    def format_post_string(post_data: dict) -> str:
        """Format the JSON string with specific spacing rules for the 'method' field"""
        post_str = json.dumps(post_data, ensure_ascii=False)
        
        if (post_data["id"] + 5) % 29 == 0 or (post_data["id"] + 3) % 13 == 0:
            post_str = post_str.replace('"method":"', '"method" : "', 1)
        else:
            post_str = post_str.replace('"method":"', '"method": "', 1)
        
        return post_str

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

    # Convert make_deepl_request to async
    async def make_deepl_request(self, post_str: str,
                                url_method: str = "LMT_handle_jobs") -> dict:
        url = f"{self.url}?client=chrome-extension,1.28.0&method={url_method}"

        try:
            response = await self.client.post(url, content=post_str)
            
            if not response.is_success:
                return {'error': response.text}
                
            try:
                return response.json()
            except Exception:
                return json.loads(brotli.decompress(response.content))
                
        except Exception as e:
            return {'error': str(e)}

    # Convert translation methods to async
    async def deepl_split_text(self, text: str, tag_handling: Optional[bool] = None) -> dict:
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
        return await self.make_deepl_request(post_str, url_method="LMT_split_text")

    async def deepl_translate(self, text, source_lang='auto', target_lang='en', preferred_num_beams=4, tag_handling=None):
        """
        Translate text using DeepL's service.
        
        Args:
            text (str): Text to translate
            source_lang (str): Source language code (default: 'auto')
            target_lang (str): Target language code (default: 'en')
            preferred_num_beams (int): Number of translation alternatives to generate
            tag_handling (bool): Whether to handle HTML tags
            
        Returns:
            dict: Translation response or error message
        """
        if not text:
            return {'error': 'No text to translate'}
            
        split_result = await self.deepl_split_text(text, tag_handling)
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
        return await self.make_deepl_request(post_str, url_method="LMT_handle_jobs")

# FastAPI routes
@app.get("/")
async def root():
    return {"code": 200, "msg": "Go to /translate with POST."}

@app.post("/translate", response_model=TranslationResponse)
async def translate(
    request: TranslationRequest,
    token_verified: bool = Depends(verify_token),
):
    """
    Handle translation requests.
    
    Args:
        request (TranslationRequest): Translation request parameters
        token_verified (bool): Token verification result from dependency
        
    Returns:
        TranslationResponse: Translation results
        
    Raises:
        HTTPException: If translation fails
    """
    translator = DeepLX(http_proxy=PROXY)
    
    # Handle text input (either string or list)
    text = request.text[0] if isinstance(request.text, list) else request.text
    
    deepl_response = await translator.deepl_translate(
        text,
        request.source_lang,
        request.target_lang
    )
    
    if 'error' in deepl_response:
        raise HTTPException(status_code=400, detail=deepl_response['error'])
    
    return translator.deepl_response_to_deeplx(deepl_response)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    