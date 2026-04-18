import requests
from bs4 import BeautifulSoup
from court_case_detect.detect import detect
from mongo_client import get_mongo_collection
from datetime import datetime

API_URL = "http://localhost:3001/court/getAll"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2OTQ4MmIzYzYxOGEyMDk2NTMxN2EyOTgiLCJzZXNzaW9uSWQiOiJjMjQ0OTFlNy01Y2VhLTQwZjYtOGFkMi0xMTliNmQwY2RjMGMiLCJpYXQiOjE3NzY1MjY0ODN9.1GLUHdKtXphzrjKEeeY6h1ijXlCh0PjHrHUstKXiIn0"


def get_court_cases(page=1, limit=1, keyword=""):
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    payload = {"page": page, "limit": limit, "keyword": keyword}

    try:
        response = requests.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()

        if data.get("status"):
            return data.get("data", {})
        else:
            print("API Error:", data.get("message"))
            return None

    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        return None


def main():
    page = 1
    limit = 100
    total_cases = 0
    collection = get_mongo_collection(tablename="court_hearings")

    while True:
        result = get_court_cases(page=page, limit=limit, keyword="")

        if not result:
            break

        items = result.get("items", [])

        if not items:
            break

        print(f"Processing page {page}...")

        for item in items:
            html_content = item.get("html") or item.get("content")

            if html_content:
                view_soup = BeautifulSoup(html_content, "html.parser")

                cases = detect(
                    view_soup,
                    {"value": item.get("courtText"), "text": item.get("court")},
                )

                # override createDate and updateDate for each case
                if cases:
                    for c in cases:
                        c["createDate"] = item["createDate"]
                        c["updateDate"] = item["updateDate"]
                if cases:
                    collection.insert_many(cases, ordered=False)

                count = len(cases) if cases else 0
                total_cases += count
                print("Total cases (this item):", count)

            print("-" * 50)

        page += 1

    print("==== GRAND TOTAL CASES ====")
    print(total_cases)


if __name__ == "__main__":
    main()
