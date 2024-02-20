from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import requests
import re

app = Flask(__name__)


# Function to scrape prices from the provided URLs
# def scrape_prices(product_name, urls):
#     prices = {}
#     for url in urls:
#         response = requests.get(url)
#         soup = BeautifulSoup(response.text, 'html.parser')
#
#         # Check if the URL is from MediaMarkt
#         if 'mediamarkt.nl' in url:
#             product_name_found = soup.find('h1', class_='product-name').text.strip()
#             if product_name.lower() in product_name_found.lower():
#                 price_element = soup.find('span', class_='price-container__value')
#                 if price_element:
#                     price = price_element.text.strip()
#                     prices[url] = price
#
#         # Check if the URL is from PlayStation Direct
#         elif 'playstation.com' in url:
#             product_name_found = soup.find('h1', class_='psw-heading-beta').text.strip()
#             if product_name.lower() in product_name_found.lower():
#                 price_element = soup.find('div', class_='price-display__price')
#                 if price_element:
#                     price = price_element.text.strip()
#                     prices[url] = price
#
#         # Add more conditions for other websites if needed
#
#         else:
#             print(f"Unsupported website: {url}")
#
#     return prices


# Function to scrape prices from the provided URLs


# Function to scrape prices from the provided URLs
def scrape_prices(product_name, urls):
    prices = {}
    for url in urls:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract product name from the webpage
        product_name_found = soup.find('h1').text.strip()  # Example: Look for <h1> tag for product name

        # Check if the provided product name is a substring of the product name found on the webpage
        if product_name.lower() in product_name_found.lower():
            # Extract price using a regular expression
            price_pattern = r'\d+\.\d+'  # Example regular expression to match prices like $99.99
            price_matches = re.findall(price_pattern, response.text)
            if price_matches:
                price = price_matches[0]
                prices[url] = price
        else:
            print(f"Product '{product_name}' not found on {url}")

    return prices



@app.route('/')
def index():
    return render_template('index.html')


@app.route('/track', methods=['POST'])
def track_prices():
    product_name = request.form['product_name']
    urls = request.form['urls'].split("\n")  # Split by newline to allow multiple URLs
    urls = [url.strip() for url in urls]  # Remove leading/trailing whitespace from URLs
    prices = scrape_prices(product_name, urls)
    if prices:
        lowest_price_url = min(prices, key=prices.get)
        lowest_price = prices[lowest_price_url]
        return render_template('result.html', lowest_price=lowest_price, lowest_price_url=lowest_price_url)
    else:
        return "No prices found"


if __name__ == '__main__':
    app.run(debug=True)
