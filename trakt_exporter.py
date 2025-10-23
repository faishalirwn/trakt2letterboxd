#!/usr/bin/env python3
"""
Trakt.tv to Letterboxd CSV Exporter
Exports your Trakt movies, ratings, and reviews to CSV for Letterboxd import
"""

import requests
import csv
import json
from datetime import datetime
import sys


class TraktExporter:
    def __init__(self, username, client_id):
        self.username = username
        self.client_id = client_id
        self.base_url = "https://api.trakt.tv"
        self.headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": client_id,
        }

    def make_request(self, endpoint, params=None):
        """Make a request to Trakt API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}")
            return None

    def format_date(self, date_str):
        """Format date for Letterboxd (YYYY-MM-DD)"""
        if not date_str:
            return ""
        try:
            # Parse ISO datetime and return just the date part
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except:
            return ""

    def convert_rating(self, trakt_rating):
        """Convert Trakt rating (1-10) to Letterboxd rating (0.5-5.0)"""
        if not trakt_rating:
            return ""
        
        # Trakt: 1-10 (integers only)
        # Letterboxd: 0.5-5.0 (half-star increments)
        # Simple division by 2
        letterboxd_rating = trakt_rating / 2.0
        
        # Format to one decimal place
        return f"{letterboxd_rating:.1f}"

    def escape_csv_field(self, field):
        """Properly escape CSV fields"""
        if not field:
            return ""
        field = str(field)
        # If field contains quotes, commas, or newlines, wrap in quotes and escape quotes
        if '"' in field or "," in field or "\n" in field:
            return f'"{field.replace(chr(34), chr(34) + chr(34))}"'
        return field

    def get_watched_movies(self):
        """Get all watched movies"""
        print("📺 Fetching watched movies...")
        return self.make_request(f"/users/{self.username}/watched/movies")

    def get_rated_movies(self):
        """Get all rated movies"""
        print("⭐ Fetching movie ratings...")
        return self.make_request(f"/users/{self.username}/ratings/movies")

    def get_movie_reviews(self, debug=False):
        """Get movie reviews and comments for movies"""
        print("📝 Fetching movie comments...")
        # Get all comments for movies specifically
        comments = self.make_request(f"/users/{self.username}/comments/all/movie")
        if not comments:
            return []

        if debug:
            print(f"\n🔍 DEBUG: Raw comments response:")
            print(json.dumps(comments[:2], indent=2))  # Show first 2 for debugging
            print(f"Total comments fetched: {len(comments)}")

        # Extract movie comments - include both reviews and regular comments
        movie_comments = []
        for item in comments:
            if item.get("type") == "movie" and item.get("comment"):
                comment_data = item.get("comment", {})
                movie_id = item["movie"]["ids"]["trakt"]
                comment_text = comment_data.get("comment", "")

                if debug:
                    print(
                        f"Movie: {item['movie']['title']} - Comment: {comment_text[:50]}..."
                    )
                    print(f"  Review flag: {comment_data.get('review', False)}")

                movie_comments.append(
                    {
                        "movie_id": movie_id,
                        "comment": comment_text,
                        "is_review": comment_data.get("review", False),
                        "spoiler": comment_data.get("spoiler", False),
                    }
                )

        print(f"Found {len(movie_comments)} movie comments/reviews")
        return movie_comments

    def export_to_csv(self, filename=None, debug=False):
        """Export Trakt data to Letterboxd CSV format"""
        if not filename:
            filename = f"{self.username}_trakt_to_letterboxd.csv"

        print(f"🚀 Starting export for user: {self.username}")

        # Test API connection
        print("🔗 Testing API connection...")
        user_data = self.make_request(f"/users/{self.username}")
        if not user_data:
            print("❌ Failed to connect to Trakt API. Check username and client ID.")
            return False

        print(f"✅ Connected! User: {user_data.get('name', self.username)}")

        # Fetch all data
        watched_movies = self.get_watched_movies()
        rated_movies = self.get_rated_movies()
        movie_comments = self.get_movie_reviews(debug=debug)

        if not watched_movies and not rated_movies:
            print("❌ No movies found for this user")
            return False

        # Create lookup maps
        ratings_map = {}
        if rated_movies:
            for item in rated_movies:
                movie_id = item["movie"]["ids"]["trakt"]
                ratings_map[movie_id] = {
                    "rating": item["rating"],
                    "rated_at": item["rated_at"],
                }

        # Create comments/reviews map - prefer reviews over regular comments
        comments_map = {}
        if movie_comments:
            # Sort by review status (reviews first) and then by length (longer comments first)
            sorted_comments = sorted(
                movie_comments, key=lambda x: (not x["is_review"], -len(x["comment"]))
            )

            for comment_data in sorted_comments:
                movie_id = comment_data["movie_id"]
                if (
                    movie_id not in comments_map
                ):  # Only take the first (best) comment per movie
                    comments_map[movie_id] = comment_data["comment"]

        if debug and comments_map:
            print(f"\n🔍 DEBUG: Comments map sample:")
            for movie_id, comment in list(comments_map.items())[:3]:
                print(f"Movie ID {movie_id}: {comment[:100]}...")

        # Prepare CSV data
        csv_data = []
        processed_movies = set()

        # Process watched movies
        if watched_movies:
            for item in watched_movies:
                movie = item["movie"]
                movie_id = movie["ids"]["trakt"]

                if movie_id in processed_movies:
                    continue
                processed_movies.add(movie_id)

                rating_info = ratings_map.get(movie_id, {})
                review = comments_map.get(movie_id, "")

                csv_data.append(
                    {
                        "Title": movie["title"],
                        "Year": movie.get("year", ""),
                        "Directors": "",  # Trakt watched endpoint doesn't include directors
                        "WatchedDate": self.format_date(item.get("last_watched_at")),
                        "Rating": self.convert_rating(rating_info.get("rating")),
                        "Review": review,
                        "Tags": "",
                        "tmdbID": movie["ids"].get("tmdb", ""),
                        "imdbID": movie["ids"].get("imdb", ""),
                    }
                )

        # Process any rated movies not in watched list
        if rated_movies:
            for item in rated_movies:
                movie = item["movie"]
                movie_id = movie["ids"]["trakt"]

                if movie_id in processed_movies:
                    continue
                processed_movies.add(movie_id)

                review = comments_map.get(movie_id, "")

                csv_data.append(
                    {
                        "Title": movie["title"],
                        "Year": movie.get("year", ""),
                        "Directors": "",
                        "WatchedDate": self.format_date(item.get("rated_at")),
                        "Rating": self.convert_rating(item["rating"]),
                        "Review": review,
                        "Tags": "",
                        "tmdbID": movie["ids"].get("tmdb", ""),
                        "imdbID": movie["ids"].get("imdb", ""),
                    }
                )

        if not csv_data:
            print("❌ No movie data to export")
            return False

        # Write CSV file
        print(f"💾 Writing CSV file: {filename}")
        try:
            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "Title",
                    "Year",
                    "Directors",
                    "WatchedDate",
                    "Rating",
                    "Review",
                    "Tags",
                    "tmdbID",
                    "imdbID",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for row in csv_data:
                    writer.writerow(row)

            print(f"✅ Export completed!")
            print(f"📊 Exported {len(csv_data)} movies")
            if comments_map:
                print(f"💬 Found comments/reviews for {len(comments_map)} movies")
            print(f"📁 File saved as: {filename}")
            print(f"📤 Import this file to Letterboxd via Settings → Import & Export")
            return True

        except Exception as e:
            print(f"❌ Error writing CSV file: {e}")
            return False


def main():
    print("🎬 Trakt.tv to Letterboxd CSV Exporter")
    print("=" * 40)

    # Get user input
    username = input("Enter your Trakt username: ").strip()
    if not username:
        print("❌ Username is required")
        sys.exit(1)

    print("\nTo get your Client ID:")
    print("1. Go to https://trakt.tv/oauth/applications")
    print("2. Create a new application")
    print("3. Copy the Client ID\n")

    client_id = input("Enter your Trakt Client ID: ").strip()
    if not client_id:
        print("❌ Client ID is required")
        sys.exit(1)

    # Ask about debug mode
    debug_input = (
        input("\nEnable debug mode to see API responses? (y/N): ").strip().lower()
    )
    debug = debug_input in ["y", "yes"]

    if debug:
        print("🐛 Debug mode enabled - API responses will be logged")

    # Export data
    exporter = TraktExporter(username, client_id)
    success = exporter.export_to_csv(debug=debug)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()