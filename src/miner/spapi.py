import re
import time
from datetime import datetime, timezone

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from dotenv import load_dotenv
import os

from src.db import get_db

load_dotenv()

SP_API_REFRESH_TOKEN = os.getenv("SP_API_REFRESH_TOKEN")
SP_API_LWA_APP_ID = os.getenv("SP_API_LWA_APP_ID")
SP_API_LWA_CLIENT_SECRET = os.getenv("SP_API_LWA_CLIENT_SECRET")
SP_API_AWS_ACCESS_KEY = os.getenv("SP_API_AWS_ACCESS_KEY")
SP_API_AWS_SECRET_KEY = os.getenv("SP_API_AWS_SECRET_KEY")
SP_API_ROLE_ARN = os.getenv("SP_API_ROLE_ARN")
SP_API_MARKETPLACE_ID = os.getenv("SP_API_MARKETPLACE_ID", "ATVPDKIKX0DER")

_lwa_cache = {"token": None, "expires_at": 0}

STOPWORDS = {"the", "and", "for", "with", "this", "that", "your", "our", "from", "are", "was", "has", "have"}


def get_lwa_token() -> str:
    now = time.time()
    if _lwa_cache["token"] and now < _lwa_cache["expires_at"]:
        return _lwa_cache["token"]

    resp = httpx.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": SP_API_REFRESH_TOKEN,
            "client_id": SP_API_LWA_APP_ID,
            "client_secret": SP_API_LWA_CLIENT_SECRET,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    _lwa_cache["token"] = data["access_token"]
    _lwa_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
    return _lwa_cache["token"]


def assume_role(role_arn: str) -> dict:
    sts = boto3.client(
        "sts",
        aws_access_key_id=SP_API_AWS_ACCESS_KEY,
        aws_secret_access_key=SP_API_AWS_SECRET_KEY,
    )
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName="spapi-miner")
    return resp["Credentials"]


def _signed_headers(method: str, url: str, params: dict, creds: dict) -> dict:
    credentials = Credentials(
        access_key=creds["AccessKeyId"],
        secret_key=creds["SecretAccessKey"],
        token=creds["SessionToken"],
    )
    request = AWSRequest(method=method, url=url, params=params)
    SigV4Auth(credentials, "execute-api", "us-east-1").add_auth(request)
    return dict(request.headers)


def search_catalog_items(keyword: str, marketplace_id: str = None, page_size: int = 20) -> list[dict]:
    marketplace_id = marketplace_id or SP_API_MARKETPLACE_ID
    creds = assume_role(SP_API_ROLE_ARN)
    lwa_token = get_lwa_token()

    url = "https://sellingpartnerapi-na.amazon.com/catalog/2022-04-01/items"
    params = {
        "keywords": keyword,
        "marketplaceIds": marketplace_id,
        "includedData": "summaries,attributes",
        "pageSize": str(page_size),
    }

    headers = _signed_headers("GET", url, params, creds)
    headers["x-amz-access-token"] = lwa_token
    headers["Accept-Encoding"] = "gzip"

    resp = httpx.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("items", []):
        asin = item.get("asin", "")
        summaries = item.get("summaries", [{}])
        s = summaries[0] if summaries else {}
        title = s.get("itemName", "")
        brand = s.get("brand", "")
        bullets = [
            bp.get("value", "")
            for bp in item.get("attributes", {}).get("bullet_point", [])
        ]
        results.append({"asin": asin, "title": title, "brand": brand, "bullets": bullets})

    return results


def _tokenize(text: str) -> list[str]:
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def mine_competitors(db_path: str, keywords_limit: int = 50):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT id, phrase FROM keywords ORDER BY autocomplete_rank ASC LIMIT ?",
        (keywords_limit,),
    ).fetchall()

    print(f"Mining {len(rows)} keywords")
    now = datetime.now(timezone.utc).isoformat()

    for kw_id, phrase in rows:
        print(f"  Searching: {phrase}")
        try:
            items = search_catalog_items(phrase)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        for item in items:
            conn.execute(
                """
                INSERT INTO asins (asin, brand, title, captured)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(asin) DO UPDATE SET
                    brand = excluded.brand,
                    title = excluded.title,
                    captured = excluded.captured
                """,
                (item["asin"], item["brand"], item["title"], now),
            )

            all_text = " ".join([item["title"]] + item["bullets"])
            tokens = _tokenize(all_text)
            for token in set(tokens):
                conn.execute(
                    """
                    INSERT INTO keywords (phrase, source, cross_listing_freq, first_seen, updated)
                    VALUES (?, 'miner', 1, ?, ?)
                    ON CONFLICT(phrase) DO UPDATE SET
                        cross_listing_freq = cross_listing_freq + 1,
                        updated = excluded.updated
                    """,
                    (token, now, now),
                )

        conn.commit()

    conn.close()
    print("Done.")


if __name__ == "__main__":
    mine_competitors("data/keywords.db")
