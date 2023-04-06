from .common import InfoExtractor
import json


class FortellerIE(InfoExtractor):
    # Google App Key, required for login
    _API_KEY = "AIzaSyAs2zSk1Xx-yq6pu4GNCqOUPLuCD1HPDYo"
    # Static Subscription Key, belongs to the app not the user
    _SUBSCRIPTION_KEY = "d025d5c78feb48fe9331d8f7efc87ea0"
    _ENDPOINTS = {
        "catalog": "https://api.forteller.io/catalog/games",
        "chapters": "https://api.forteller.io/catalog/games/{0}/containers",
        "tracks": "https://api.forteller.io/catalog/games/{0}/containers/{1}/playlist",
        "stream-key": "https://api.forteller.io/media/streamkey/{0}?playlistId={1}",
    }
    _VALID_URL = r"https?://(?:www\.)?fortellergames\.com/(?P<id>\w+)"
    _NETRC_MACHINE = "forteller"
    _TOKEN = None

    def _perform_login(self, username, password):
        data = json.dumps(
            {"email": username, "password": password, "returnSecureToken": True}
        ).encode("utf-8")
        url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={self._API_KEY}"
        self._TOKEN = self._download_json(
            url,
            None,
            note="Logging in",
            data=data,
            headers={
                "content-type": "application/json",
                "Forteller-Subscription-Key": self._SUBSCRIPTION_KEY,
            },
        )["idToken"]

    def _real_initialize(self):
        if not self._TOKEN:
            self.raise_login_required(method="password")

    """
    Returns the SKU for the URL requested.
    This is needed to match the website URL
    against the API calls.
    """
    def _get_sku(self):
        sku = self.cache.load("forteller", f"sku/{self.narration_id}")
        if sku:
            return sku
        c = self._download_webpage(self.url, None, note="Downloading narration page")
        sku = self._search_regex(r"sku&quot;:&quot;(?P<sku>\w+)&quot;", c, "sku")
        self.cache.store("forteller", f"sku/{self.narration_id}", sku)
        return sku

    """
    Returns the complete catalog as a list of dicts
    """
    def _get_catalog(self):
        return self._call_api("catalog")

    """
    Returns a list of dicts with id, shortKey, name attributes
    for each of the chapters
    """
    def _get_chapters(self, game_id):
        return [
            {"id": row["id"], "shortKey": row["shortKey"], "name": row["name"]}
            for row in self._call_api("chapters", game_id)
        ]

    def _call_api(self, endpoint, *items):
        url = self._ENDPOINTS[endpoint].format(*items)
        r = self.cache.load("forteller", f"api/{url}")
        if r:
            return r
        r = self._download_json(
            url,
            None,
            note=f"Downloading {endpoint} JSON metadata",
            headers={
                "Authorization": f"Bearer {self._TOKEN}",
                "Forteller-Subscription-Key": self._SUBSCRIPTION_KEY,
            },
        )
        self.cache.store("forteller", f"api/{url}", r)
        return r

    def _get_playlist(self, game_id, chapter_id):
        return self._call_api("tracks", game_id, chapter_id)

    # Returns a dict with the game's metadata
    def _find_sku_in_catalog(self, sku) -> dict:
        return [game for game in self._get_catalog() if game["sku"] == sku][0]

    def _get_stream_key(self, track_locator_id, playlist_id):
        return self._call_api("stream-key", track_locator_id, playlist_id)["token"]

    def _track_infodict(self, metadata, chapters):
        info_tracks = []
        disc_number = 0
        for chapter in chapters:
            disc_number += 1
            playlist = self._get_playlist(metadata["id"], chapter["id"])
            track_number = 1
            for track in playlist["content"]:
                sk = self._get_stream_key(track["asset"]["locatorId"], playlist["id"])
                yield {
                    "id": track["id"],
                    "formats": self._extract_m3u8_formats(
                        f"{track['asset']['streamUrl']}(format=m3u8-aapl,encryption=cbc,type=audio)", track['id'], 'm4a',
                        'm3u8_native', m3u8_id='hls'
                    ),
                    "chapter": chapter["name"],
                    "chapter_id": playlist["id"],
                    "chapter_number": disc_number,
                    "track": track["title"],
                    "title": chapter["name"] + " - " + track["title"],
                    "track_number": track_number,
                    "artist": "Forteller Media",
                    "genre": "AudioNarration",
                    "album_artist": "Forteller Media",
                    "composer": metadata["publisher"]["name"],
                    "disc_number": disc_number,
                    "album": metadata["name"],
                    "thumbnail": metadata["storeCardUri"],
                    "http_headers": {
                        "Authorization": f"Bearer {sk}",
                    },
                }
                track_number += 1

    def _real_extract(self, url):
        self.url = url
        self.narration_id = self._match_id(url)
        sku = self._get_sku()
        metadata = self._find_sku_in_catalog(sku)
        chapters = self._get_chapters(metadata["id"])

        return {
            "id": metadata["id"],
            "title": metadata["name"],
            "_type": "playlist",
            "entries": self._track_infodict(metadata, chapters),
        }
