# Waypoint — AI Travel Planner

An AI-powered trip planner built on AWS. Give it a source city, a destination, a budget, and a number of days — it generates a full day-by-day itinerary (hotels, food, transport, weather, Google Maps links) and produces a downloadable PDF.

## Live Architecture

```
Frontend (EC2 + Nginx)
      │
      ▼
API Gateway (HTTP API)
      │
      ▼
AWS Lambda (Python)
      │
      ├──► Groq API (Llama 3.3) — generates the itinerary
      ├──► DynamoDB — stores the trip record
      └──► S3 — stores the generated PDF
```

## Tech Stack

- **Frontend**: Plain HTML/CSS/JS (single file, no build step), hosted on an EC2 instance via Nginx
- **Backend**: AWS Lambda (Python 3.12)
- **AI**: Groq API (`llama-3.3-70b-versatile`) for itinerary generation
- **Database**: DynamoDB (stores every generated trip)
- **Storage**: S3 (stores generated PDF itineraries, publicly readable)
- **API layer**: API Gateway (HTTP API)
- **PDF generation**: `reportlab` (pure Python, no headless browser needed)

## Project Structure

```
.
├── backend/
│   ├── lambda_function.py     # Lambda handler — AI call, PDF gen, S3 upload, DynamoDB save
│   └── requirements.txt       # Python dependencies (reportlab)
├── frontend/
│   └── index.html             # Full frontend — form, results, styling, API calls
└── README.md
```

## Setup — Step by Step

### 1. DynamoDB
Create a table named `TravelPlannerTrips` with partition key `tripId` (String), on-demand capacity.

### 2. S3
Create a bucket for storing generated PDFs. Disable "Block all public access" and attach this bucket policy (replace `YOUR-BUCKET-NAME`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadForPDFs",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/itineraries/*"
    }
  ]
}
```

### 3. Groq API Key
Get a free API key from [console.groq.com/keys](https://console.groq.com/keys) — no card required.

### 4. Lambda
1. Create a Python 3.12 function.
2. Install dependencies locally and package with the code:
   ```bash
   pip install reportlab -t . --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all:
   zip -r deploy.zip .
   ```
3. Upload `deploy.zip`.
4. Set **Timeout** to 30s, **Memory** to 512MB.
5. Add environment variables:
   - `DYNAMODB_TABLE` = `TravelPlannerTrips`
   - `S3_BUCKET` = your bucket name
   - `GROQ_API_KEY` = your Groq key
6. Attach an execution role with `AmazonDynamoDBFullAccess` and `AmazonS3FullAccess` (scope these down for production).

### 5. API Gateway
1. From the Lambda console, use **"+ Add trigger" → API Gateway → Create/attach an HTTP API** — this auto-configures the correct invoke permissions.
2. Enable CORS on the API:
   - `Access-Control-Allow-Origin`: `*`
   - `Access-Control-Allow-Headers`: `content-type`
   - `Access-Control-Allow-Methods`: `POST, OPTIONS`
3. Note the invoke URL — this goes into the frontend.

> **Note**: if the route uses the `ANY` method, OPTIONS preflight requests are forwarded straight to Lambda instead of being handled automatically by API Gateway. The Lambda handler in this repo already accounts for this and returns a `200` for `OPTIONS` requests.

### 6. Frontend
1. Open `frontend/index.html` and update the `API_ENDPOINT` constant near the top of the `<script>` block with your API Gateway invoke URL.
2. Deploy on an EC2 instance:
   ```bash
   sudo apt update && sudo apt install -y nginx
   sudo chown -R ubuntu:ubuntu /var/www/html
   ```
3. Upload `index.html` into `/var/www/html/` (via `scp`, FileZilla, or `git clone` directly on the instance).
4. Visit `http://<EC2-PUBLIC-IP>`.

## Environment Variables (Lambda)

| Variable | Description |
|---|---|
| `DYNAMODB_TABLE` | DynamoDB table name for storing trips |
| `S3_BUCKET` | S3 bucket name for storing generated PDFs |
| `GROQ_API_KEY` | API key for Groq (itinerary generation) |

## License

MIT
