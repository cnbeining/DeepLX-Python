# DeepLX-Python

Python implementation of [DeepLX](https://github.com/OwO-Network/DeepLX), providing a FastAPI-based translation service using DeepL.

This repo only implemented the `Free Endpoint`.

## Features

- FastAPI-based Async REST API: WSGI version provided for reference
- Docker and Compose support
- Token-based authentication
- Support for both plain text and rich text translation
- Proxy support via environment variables

## Installation

### Using Docker (Recommended)

1. Clone the repository:

```bash
git clone https://github.com/cnbeining/DeepLX-Python.git
cd DeepLX-Python
```

2. Using Docker Compose (Recommended):

```bash
# Edit docker-compose.yml to set your tokens
docker compose up -d
```

Or build and run the Docker container directly:

```bash
docker build -t deeplx-python .
docker run -d -p 8000:8000 -e TOKEN=your,tokens,here deeplx-python
```

### Manual Installation

1. Clone the repository:

```bash
git clone https://github.com/cnbeining/DeepLX-Python.git
cd DeepLX-Python
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

```bash
python app/app.py
```

## Configuration

### Environment Variables

- `TOKEN`: Comma-separated list of valid authentication tokens
- `PROXY`: Proxy URL (optional)

Example:

```bash
export TOKEN=token1,token2,token3
export PROXY=http://proxy.example.com:8080
```

## API Usage

[See DeepLX for details](https://deeplx.owo.network/endpoints/free.html)

### Authentication

Include your token either as:

- Query parameter: `?token=your_token`
- Authorization header: `Authorization: Bearer your_token` or `Authorization: DeepL-Auth-Key your_token`

### Translate Text

```bash
curl -X POST "http://localhost:8000/translate" \
-H "Authorization: Bearer your_token" \
-H "Content-Type: application/json" \
-d '{
"text": "Hello, world!",
"source_lang": "auto",
"target_lang": "es"
}'
```

### Request Parameters

- `text`: String or array of strings to translate
- `source_lang`: Source language code (default: "auto")
- `target_lang`: Target language code (default: "en")
- `tag_handling`: Optional parameter for handling HTML/XML tags. Will be automatically detected if not set.

### Response Format

```json
{
"alternatives": ["translated alternatives"],
"code": 200,
"data": "translated text",
"id": 123456,
"method": "Free",
"source_lang": "detected_language",
"target_lang": "target_language"
}
```

## License

This project is licensed under the GNU AGPL 3.0 License - see the LICENSE file for details.
