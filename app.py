from flask import Flask, render_template, request, redirect, jsonify
import requests
from bs4 import BeautifulSoup
import difflib
import re
from urllib.parse import unquote, quote_plus

app = Flask(__name__)

# Language Codes Dictionary
language_codes = {
    "tamil": "tamil",
    "hindi": "hindi",
    "telugu": "telugu",
    "malayalam": "malayalam",
    "kannada": "kannada",
    "bengali": "bengali",
    "marathi": "marathi",
    "punjabi": "punjabi"
}


def correct_spelling(user_input, valid_options):
    close_matches = difflib.get_close_matches(user_input, valid_options, n=1, cutoff=0.7)
    return close_matches[0] if close_matches else None


def clean_title(title):
    if not title:
        return None
    title = re.sub(r'^Einthusan\s*[-–—]\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(\d{4}\)\s*$', '', title)
    title = re.sub(r'\s*\[(Tamil|Hindi|Telugu|Malayalam|Kannada|Bengali|Marathi|Punjabi)\]', '', title, flags=re.IGNORECASE)
    # Updated regex to remove "(YYYY) Language in HD/SD - Einthusan" or similar
    title = re.sub(r'\s*\(\d{4}\)\s*(?:Tamil|Hindi|Telugu|Malayalam|Kannada|Bengali|Marathi|Punjabi)\s*in\s*(?:HD|SD)\s*-\s*Einthusan(?:\s*-\s*Watch Movies Online)?$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\|\s*Einthusan(?:\s*-\s*Watch Movies Online)?$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'Watch Full Movie Online Free$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'Online Watch Free (?:HD|SD)$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'Free Movies Online$', '', title, flags=re.IGNORECASE).strip()
    return title.strip()


def get_title_from_movie_page(page_url, headers):
    try:
        movie_response = requests.get(page_url, headers=headers, timeout=5)
        if movie_response.status_code == 200:
            movie_soup = BeautifulSoup(movie_response.content, 'html.parser')
            meta_og_title = movie_soup.find('meta', property='og:title')
            if meta_og_title and meta_og_title.get('content'):
                return clean_title(meta_og_title['content'])
            html_title_tag = movie_soup.find('title')
            if html_title_tag and html_title_tag.text.strip():
                return clean_title(html_title_tag.text.strip())
            h1_tag = movie_soup.find('h1')
            if h1_tag and h1_tag.text.strip():
                return clean_title(h1_tag.text.strip())
    except requests.RequestException as e:
        print(f"Failed to fetch individual movie page {page_url} for title extraction: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while processing movie page {page_url}: {e}")
    return None


def fetch_movies_by_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch {url} with status code {response.status_code}")
            return []
    except requests.RequestException as e:
        print(f"Request failed for {url}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    movies = []

    for div in soup.find_all('div', class_='block1'):
        link_tag = div.find('a')
        img_tag = div.find('img')
        title_div_tag = div.find('div', class_='title')

        if not (link_tag and img_tag):
            continue

        title = None
        # We need the full URL for Einthusan to fetch the video later
        page_url_full = f"https://einthusan.tv{link_tag['href']}"

        if title_div_tag and title_div_tag.text.strip():
            extracted_title = clean_title(title_div_tag.text.strip())
            if extracted_title and len(extracted_title) > 3 and not extracted_title.isdigit():
                title = extracted_title

        if not title and img_tag.has_attr('alt') and img_tag['alt'].strip():
            extracted_title = clean_title(img_tag['alt'].strip())
            if extracted_title and len(extracted_title) > 3 and not extracted_title.isdigit():
                title = extracted_title

        if not title and img_tag.has_attr('title') and img_tag['title'].strip():
            extracted_title = clean_title(img_tag['title'].strip())
            if extracted_title and len(extracted_title) > 3 and not extracted_title.isdigit():
                title = extracted_title

        if not title and link_tag.has_attr('href'):
            href = link_tag['href']
            if '/watch/' in href:
                try:
                    slug = href.split('/watch/')[1].split('/')[0]
                    decoded_slug = unquote(slug)
                    temp_title = ' '.join([word.capitalize() for word in decoded_slug.replace('-', ' ').split(' ') if word and not word.isdigit()])
                    if temp_title:
                        title = clean_title(temp_title)
                except Exception as e:
                    print(f"Error parsing slug from URL {href}: {e}")
            elif 'title=' in href:
                try:
                    title_part = href.split('title=')[1].split('&')[0]
                    decoded_title_part = unquote(title_part)
                    title = clean_title(decoded_title_part.replace('+', ' ').title())
                except Exception as e:
                    print(f"Error parsing title parameter from URL {href}: {e}")

        if not title or title == 'Untitled' or title == 'Untitled Movie (Title Not Found)' or (title and (title.isdigit() or len(title) <= 4)):
            print(f"Attempting to fetch title from individual page for: {page_url_full} (Previous title: {title})")
            accurate_title = get_title_from_movie_page(page_url_full, headers)
            title = accurate_title if accurate_title else 'Untitled Movie (Title Not Found)'

        movies.append({
            'title': title,
            'img_url': img_tag['src'],
            'page_url': page_url_full # This is the Einthusan movie page URL
        })

    return movies


def search_movie(language, movie_title):
    lang_code = language_codes.get(language.lower())
    if not lang_code:
        return []
    search_url = f"https://einthusan.tv/movie/results/?lang={lang_code}&query={movie_title.replace(' ', '+')}"
    return fetch_movies_by_url(search_url)


def extract_video_url(page_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(page_url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch {page_url} with status code {response.status_code}")
            return None
        soup = BeautifulSoup(response.content, 'html.parser')
        video_player = soup.find(id="UIVideoPlayer")
        if video_player:
            mp4_link = video_player.get('data-mp4-link')
            if mp4_link:
                # Assuming the structure 'etv' is always at the beginning
                video_data = mp4_link.split("etv")[1]
                return f"https://cdn1.einthusan.io/etv{video_data}"
        print(f"No video player found on {page_url} or no data-mp4-link.")
        return None
    except requests.RequestException as e:
        print(f"Request failed to extract video URL for {page_url}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during video URL extraction for {page_url}: {e}")
        return None


@app.route('/')
def index():
    return render_template('index.html', languages=language_codes.keys())


@app.route('/language/<language>')
def language_page(language):
    category = request.args.get('category', 'recent')
    page = request.args.get('page', 1, type=int)
    corrected_language = correct_spelling(language, language_codes.keys())

    if corrected_language is None:
        return render_template('index.html', error="Invalid language", languages=language_codes.keys())

    lang_code = language_codes[corrected_language]

    if category == "recent":
        url = f"https://einthusan.tv/movie/results/?find=Recent&lang={lang_code}&page={page}"
    elif category == "popular":
        url = f"https://einthusan.tv/movie/results/?find=Popularity&lang={lang_code}&ptype=view&tp=alltime&page={page}"
    else: # Default to recent if category is not recognized or is missing
        url = f"https://einthusan.tv/movie/results/?find=Recent&lang={lang_code}&page={page}"

    movies = fetch_movies_by_url(url)
    next_page = page + 1

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'movies': movies,
            'next_page': next_page,
            'has_more': len(movies) > 0 # Indicate if more movies might be available
        })

    return render_template('language.html',
                           language=corrected_language,
                           movies=movies,
                           category=category,
                           current_page=page,
                           next_page=next_page)


@app.route('/search/<language>', methods=['POST'])
def search(language):
    movie_title = request.form.get('movie_title')
    results = search_movie(language, movie_title)
    return render_template('language.html', language=language, movies=results, search=movie_title, category='')


@app.route('/watch')
def watch():
    movie_page_url = request.args.get('url') # This is the Einthusan movie page URL
    movie_title = request.args.get('title', 'Unknown Movie') # Get title from query parameter, default if not provided

    if not movie_page_url:
        return "Movie URL is missing.", 400

    video_url = extract_video_url(movie_page_url)

    if video_url:
        return render_template('watch.html', movie_title=movie_title, video_url=video_url)
    else:
        # If video_url is None, try to get a better title from the page itself if 'title' wasn't set.
        # This is a fallback in case the initial title extraction failed or was incomplete.
        if movie_title == 'Unknown Movie':
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            fetched_title = get_title_from_movie_page(movie_page_url, headers)
            if fetched_title:
                movie_title = fetched_title

        return render_template('watch.html', movie_title=movie_title, video_url=None, error="Video not found or failed to extract.")


if __name__ == '__main__':
    app.run(debug=True)