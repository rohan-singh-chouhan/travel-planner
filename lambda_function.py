import json
import os
import uuid
import io
import urllib.request
import urllib.error
from datetime import datetime, timezone

import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
BUCKET_NAME = os.environ["S3_BUCKET"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": "{}"}

    try:
        body = json.loads(event.get("body") or "{}")
        source = body.get("source")
        destination = body.get("destination")
        budget = body.get("budget")
        days = body.get("days")
        interests = body.get("interests", [])

        if not all([source, destination, budget, days]):
            return _response(400, {"error": "source, destination, budget, days zaroori hain"})

        # Step 1: OpenAI se itinerary generate karo
        itinerary = generate_itinerary(source, destination, budget, days, interests)

        # Step 2: PDF banao
        pdf_bytes = generate_pdf(itinerary, source, destination, budget, days)

        # Step 3: PDF ko S3 mein upload karo
        trip_id = str(uuid.uuid4())
        pdf_key = f"itineraries/{trip_id}.pdf"
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=pdf_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        pdf_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{pdf_key}"

        # Step 4: DynamoDB mein trip save karo
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item={
            "tripId": trip_id,
            "source": source,
            "destination": destination,
            "budget": budget,
            "days": days,
            "interests": interests,
            "itinerary": itinerary,
            "pdfUrl": pdf_url,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })

        return _response(200, {"tripId": trip_id, "itinerary": itinerary, "pdfUrl": pdf_url})

    except Exception as e:
        print("Error:", str(e))
        return _response(500, {"error": "Kuch galat ho gaya", "details": str(e)})


# ---------- OpenAI se itinerary generate karna ----------
def generate_itinerary(source, destination, budget, days, interests):
    interest_list = ", ".join(interests) if isinstance(interests, list) else str(interests)

    prompt = f"""You are an expert Indian travel planner. Based on the details below, create a detailed trip plan in JSON format.

Source: {source}
Destination: {destination}
Budget: Rs {budget}
Duration: {days} days
Interests: {interest_list}

IMPORTANT: Respond ONLY in English. Do not use Hindi or Hinglish anywhere in the response.
Return only valid JSON, no extra text. Follow this exact format:
{{
  "summary": "1-2 line trip overview",
  "weather": "expected weather during trip",
  "hotels": [{{"name": "", "pricePerNight": 0, "area": ""}}],
  "transport": {{"toDestination": "", "local": "", "estimatedCost": 0}},
  "days": [
    {{
      "day": 1,
      "title": "",
      "activities": [{{"time": "", "place": "", "description": "", "googleMapsLink": "https://www.google.com/maps/search/?api=1&query=PLACE_NAME"}}],
      "food": ["restaurant/dish suggestions"],
      "estimatedCost": 0
    }}
  ],
  "totalEstimatedCost": 0,
  "budgetNote": "whether the trip is possible within budget, with tips"
}}"""

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "Mozilla/5.0 (compatible; TravelPlannerLambda/1.0)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise Exception(f"Groq API error: {err_body}")

    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


# ---------- PDF generate karna ----------
def generate_pdf(itinerary, source, destination, budget, days):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - 50
    line_height = 16
    max_width = width - 2 * margin

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 50

    def add_text(text, size=11, bold=False, color=black):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.setFillColor(color)
        words = str(text).split(" ")
        line = ""
        for word in words:
            test_line = f"{line}{word} "
            if c.stringWidth(test_line, "Helvetica-Bold" if bold else "Helvetica", size) > max_width:
                if y < 60:
                    new_page()
                    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
                    c.setFillColor(color)
                c.drawString(margin, y, line)
                y -= line_height
                line = f"{word} "
            else:
                line = test_line
        if y < 60:
            new_page()
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            c.setFillColor(color)
        c.drawString(margin, y, line)
        y -= line_height + 4

    blue = HexColor("#1a4d99")
    green = HexColor("#1a8033")

    add_text(f"Trip Plan: {source} to {destination}", 18, True, blue)
    add_text(f"Duration: {days} days | Budget: Rs {budget}", 11)
    add_text(itinerary.get("summary", ""), 11)
    add_text(f"Weather: {itinerary.get('weather', 'N/A')}", 11)
    y -= 6

    add_text("Hotels", 14, True)
    for h in itinerary.get("hotels", []):
        add_text(f"- {h.get('name','')} ({h.get('area','')}) - Rs {h.get('pricePerNight',0)}/night", 11)
    y -= 6

    add_text("Transport", 14, True)
    transport = itinerary.get("transport", {})
    add_text(f"To destination: {transport.get('toDestination', 'N/A')}", 11)
    add_text(f"Local transport: {transport.get('local', 'N/A')}", 11)
    y -= 6

    for d in itinerary.get("days", []):
        add_text(f"Day {d.get('day','')}: {d.get('title','')}", 14, True, blue)
        for a in d.get("activities", []):
            add_text(f"  {a.get('time','')} - {a.get('place','')}: {a.get('description','')}", 10)
        food = d.get("food", [])
        if food:
            add_text(f"  Food: {', '.join(food)}", 10)
        add_text(f"  Estimated cost: Rs {d.get('estimatedCost', 0)}", 10)
        y -= 4

    y -= 6
    add_text(f"Total Estimated Cost: Rs {itinerary.get('totalEstimatedCost', 0)}", 14, True, green)
    add_text(itinerary.get("budgetNote", ""), 10)

    c.save()
    buffer.seek(0)
    return buffer.read()


def _response(status_code, body_obj):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_obj),
    }
