import os
import requests
from data import scbcList
import time
from pyairtable import Api
from colorama import init, Fore, Style
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize colorama for automatic reset after each print
init(autoreset=True)

# Define your API key, Base ID, Table Name, OpenAI key, and Scraper key from environment variables
api_key = os.getenv('airtable_api_key')
base_id = os.getenv('airtable_base_id')
table_name = os.getenv('airtable_table_name')
openai_key = os.getenv('openai_key')
scraper_key = os.getenv('scraper_key')

# Initialize Airtable API
api = Api(api_key)
table = api.table(base_id, table_name)

def convert_to_hourly(salary):
    threshold = 500
    hours_per_year = 2080

    try:
        salary = float(salary)
    except ValueError:
        print(Fore.RED + "ERROR CONVERTING SALARY TO per hour")
        return "skip"

    if salary > threshold:
        hourly_rate = salary / hours_per_year
    else:
        hourly_rate = salary

    return round(hourly_rate, 2)

def generate_response(messages, model="gpt-4o-mini", temperature=0.7, max_tokens=500):
    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}"
    }

    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = requests.post(endpoint, headers=headers, json=data)
    
    if response.status_code == 200:
        gptData = response.json()
        text = gptData['choices'][0]['message']['content']
        return text
    else:
        print(Fore.RED + "Error:", response.text)
        return "skip"

def check_if_exists(applicationLink):
    try:
        # Search for records with the given id (applicationLink)
        records = table.all(formula=f"{{id}}='{applicationLink}'")
        return len(records) > 0
    except Exception as e:
        print(Fore.RED + "Error checking record existence:", str(e))
        return False

counter = 0

for key in scbcList:
    print(Fore.YELLOW + "Starting new data collection procedure for: " + scbcList[key]['name'])

    url = "https://linkedin-data-scraper.p.rapidapi.com/company_jobs"

    payload = {
        "company_url": f"http://www.linkedin.com/company/{key}",
        "count": 100
    }
    print(payload)
    headers = {
        "x-rapidapi-key": scraper_key,
        "x-rapidapi-host": "linkedin-data-scraper.p.rapidapi.com",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    jobData = response.json()

    if jobData["status"] == 200:
        print(Fore.YELLOW + "Data collection successful")

        for job in jobData["response"]["data"]["jobs"]:
            print(Fore.YELLOW + "Total of jobs: ", len(jobData["response"]["data"]["jobs"]))
            print(Fore.YELLOW + f'Starting {job["title"]} @ {job["companyName"]}')
            
            # Determine the correct application link
            applicationLink = job["companyApplyUrl"] if job["companyApplyUrl"] else job["jobPostingUrl"]

            # Check the country and skip if it's not "us"
            if job["country"].lower() != "us":
                print(Fore.YELLOW + f"Skipping non-US job: {job['title']} @ {job['companyName']}")
                continue

            # Check if the record already exists
            if check_if_exists(applicationLink):
                print(Fore.YELLOW + f"Job already exists in Airtable. Skipping: {job['title']} @ {job['companyName']}")
                continue

            # Prepare data for Airtable
            title = job["title"]
            company_name = job["companyName"]
            location = job["formattedLocation"]

            try:
                stablePromptRequestTemplate = f'''
                Job Title: {title}
                Company Name: {company_name}
                Location: {location}
                
                Based on the given information, generate an hourly salary estimate for this job posting, in the format of "minimum-maximum" hourly salary range (e.g. 21.5-24.5). Reply only with the salary range, and do not include a dollar sign in your response with the salary values or any other information, details or text.
                ''' 
                salary = generate_response([
                    {"role": "system", "content": "You are an AI that will estimate an hourly salary range (minimum-maximum) for a provided job posting."},
                    {"role": "user", "content": stablePromptRequestTemplate}
                ], model="gpt-4o-mini", temperature=0.65, max_tokens=500)
                print(Fore.YELLOW + "No Job salary provided... AI salary prediction is - ", salary)
            except:
                print(Fore.RED + "No Job salary- AI SALARY FAILED - ", jobData.get('salary', 'N/A'))
                salary = "skip"

            airtable_data = {
                "company": company_name,
                "description": job["jobDescription"],
                "externalApplyLink": applicationLink,
                "location": location,
                "positionName": title,
                "salary": salary,
                "url": applicationLink,
                "id": applicationLink,
            }

            print(Fore.YELLOW + "Adding record to Airtable")

            # Send the POST request to add the record
            start = time.time()
            response = table.create(airtable_data)
            end = time.time()
            print(Fore.GREEN + f"Time taken: {end - start}")
            print(response)

    else:
        print(Fore.RED + "Data collection failed, status code:", jobData["status"])
        continue
