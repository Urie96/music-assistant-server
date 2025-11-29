from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry
from music_assistant_models.enums import (
    ConfigEntryType,
    ContentType,
    ImageType,
    MediaType,
    ProviderFeature,
    StreamType,
)
from music_assistant_models.media_items import (
    Album,
    Artist,
    AudioFormat,
    MediaItemImage,
    Playlist,
    ProviderMapping,
    RecommendationFolder,
    SearchResults,
    Track,
)
from music_assistant_models.streamdetails import StreamDetails

from music_assistant.controllers.cache import use_cache
from music_assistant.models.music_provider import MusicProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import (
        ConfigValueType,
        ProviderConfig,
    )
    from music_assistant_models.provider import ProviderManifest

    from music_assistant.mass import MusicAssistant
    from music_assistant.models import ProviderInstanceType


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    # setup is called when the user wants to setup a new provider instance.
    # you are free to do any preflight checks here and but you must return
    #  an instance of the provider.
    return NeteaseCloudProvider(mass, manifest, config)


CONF_API_HOST = "api_host"
CONF_UID = "uid"


async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """
    Return Config entries to setup this provider.

    instance_id: id of an existing provider instance (None if new instance setup).
    action: [optional] action key called from config entries UI.
    values: the (intermediate) raw values for config entries sent with the action.
    """
    return (
        ConfigEntry(
            key=CONF_API_HOST,
            type=ConfigEntryType.STRING,
            label="API Host",
            required=True,
        ),
        ConfigEntry(
            key=CONF_UID,
            type=ConfigEntryType.SECURE_STRING,
            label="User ID",
            required=True,
        ),
    )


class NeteaseCloudProvider(MusicProvider):
    """Provider for Netease Cloud Music."""

    _api_host: str = ""
    _uid: str = ""

    @property
    def supported_features(self) -> set[ProviderFeature]:
        """Return the features supported by this Provider."""
        return {
            ProviderFeature.SEARCH,
            ProviderFeature.RECOMMENDATIONS,
            ProviderFeature.LIBRARY_PLAYLISTS,
            ProviderFeature.ARTIST_ALBUMS,
            ProviderFeature.ARTIST_TOPTRACKS,
        }

    async def handle_async_init(self) -> None:
        self._api_host = self.config.get_value(CONF_API_HOST)
        self._uid = self.config.get_value(CONF_UID)

    @property
    def is_streaming_provider(self) -> bool:
        return True

    async def search(  # type: ignore[empty-body]
        self,
        search_query: str,
        media_types: list[MediaType],
        limit: int = 5,
    ) -> SearchResults:
        """Perform search on musicprovider."""
        resp = await self._call_api(f"/search?keywords={search_query}&limit={limit}")
        return SearchResults(
            tracks=[self._parse_track(track) for track in resp["result"]["songs"]],
        )

    async def get_library_playlists(self) -> AsyncGenerator[Playlist, None]:
        """Retrieve library/subscribed playlists from the provider."""
        data = await self._call_api(f"/user/playlist?uid={self._uid}")
        for playlist in data["playlist"]:
            yield self._parse_playlist(playlist)

    @use_cache(3600 * 24 * 30)
    async def get_artist(self, prov_artist_id: str) -> Artist:
        """Get full artist details by id."""
        data = await self._call_api(f"/artist/detail?id={prov_artist_id}")
        return self._parse_artist(data["data"]["artist"])

    @use_cache(3600 * 24 * 30)
    async def get_artist_albums(self, prov_artist_id: str) -> list[Album]:
        """Get a list of all albums for the given artist."""
        data = await self._call_api(f"/artist/album?id={prov_artist_id}&limit=10")
        return [self._parse_album(track) for track in data["hotAlbums"]]

    @use_cache(3600 * 24 * 30)
    async def get_artist_toptracks(self, prov_artist_id: str) -> list[Track]:
        """Get a list of most popular tracks for the given artist."""
        data = await self._call_api(f"/artists?id={prov_artist_id}")
        return await self._parse_tracks(data["hotSongs"])

    @use_cache(3600 * 24 * 30)
    async def get_album(self, prov_album_id: str) -> Album:
        """Get full album details by id."""
        data = await self._call_api(f"/album?id={prov_album_id}")
        return self._parse_album(data["album"])

    @use_cache(3600 * 24 * 30)
    async def get_track(self, prov_track_id: str) -> Track:
        """Get full track details by id."""
        data = await self._call_api(f"/song/detail/?ids={prov_track_id}")
        return self._parse_track(data["songs"][0])

    @use_cache(3600 * 24)
    async def get_playlist(self, prov_playlist_id: str) -> Playlist:
        """Get full playlist details by id."""
        data = await self._call_api(f"/playlist/detail?id={prov_playlist_id}")
        return self._parse_playlist(data["playlist"])

    @use_cache(3600 * 24 * 30)
    async def get_album_tracks(
        self,
        prov_album_id: str,
    ) -> list[Track]:
        """Get album tracks for given album id."""
        data = await self._call_api(f"/album?id={prov_album_id}")
        return await self._parse_tracks(data["songs"])

    @use_cache(3600 * 24)
    async def get_playlist_tracks(
        self,
        prov_playlist_id: str,
        page: int = 0,
    ) -> list[Track]:
        """Get all playlist tracks for given playlist id."""
        limit = 20
        data = await self._call_api(
            f"/playlist/track/all?id={prov_playlist_id}&limit={limit}&offset={page * limit}"
        )
        return await self._parse_tracks(data["songs"])

    async def get_stream_details(self, item_id: str, media_type: MediaType) -> StreamDetails:
        """Get streamdetails for a track/radio."""
        data = await self._call_api(f"/song/url/v1?id={item_id}&level=exhigh")
        return StreamDetails(
            provider=self.instance_id,
            item_id=item_id,
            audio_format=AudioFormat(
                content_type=ContentType.UNKNOWN,
            ),
            media_type=MediaType.TRACK,
            stream_type=StreamType.HTTP,
            allow_seek=True,
            can_seek=True,
            path=data["data"][0]["url"],
        )

    async def resolve_image(self, path: str) -> str | bytes:
        """Resolve an image from an image path."""
        return path

    @use_cache(3600 * 24)
    async def recommendations(self) -> list[RecommendationFolder]:
        """Get this provider's recommendations."""
        res: RecommendationFolder = RecommendationFolder(
            item_id="netease_cloud_recommend",
            provider=self.domain,
            name="网易云推荐",
        )
        res.items.append(
            self._parse_playlist(
                {
                    "id": "3778678",
                    "name": "热歌榜",
                    "coverImgUrl": "https://p3.music.126.net/0SUEG8yDACfx0Bw2MYFv4Q==/109951170048519512.jpg",
                }
            )
        )
        data = await self._call_api("/personalized?limit=5")
        if data["result"] and data["result"][0]:
            for playlist in data["result"]:
                res.items.append(self._parse_playlist(playlist))
        return [res]

    @use_cache(3600 * 24 * 30)
    async def _track_available(self, prov_track_id: str) -> bool:
        try:
            data = await self._call_api(f"/check/music?id={prov_track_id}")
            self.logger.debug("track %s available %s", prov_track_id, data["success"])
            return data["success"]
        except:
            self.logger.warning("track %s check available error", prov_track_id)
            return True

    async def _call_api(self, path: str):
        async with self.mass.http_session.get(
            f"{self._api_host}{path}",
        ) as response:
            return await response.json()

    async def _parse_tracks(self, objs: list[dict]) -> list[Track]:
        self.logger.debug("parsing %d tracks", len(objs))
        semaphore = asyncio.Semaphore(10)

        async def parse(obj: dict):
            if str(obj.get("fee", "0")) == "0":  # 免费或无版权
                async with semaphore:
                    available = await self._track_available(str(obj["id"]))
                    if not available:
                        return None
            return self._parse_track(obj)

        tasks = [parse(obj) for obj in objs]
        results = await asyncio.gather(*tasks)
        return [result for result in results if result is not None]

    def _parse_track(self, obj: dict) -> Track:
        track_id = str(obj["id"])
        track = Track(
            item_id=track_id,
            provider=self.instance_id,
            name=obj["name"],
            provider_mappings={
                ProviderMapping(
                    item_id=track_id,
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
        )
        if "al" in obj:
            track.album = self._parse_album(obj["al"])

        if "ar" in obj:
            for artist in obj["ar"]:
                track.artists.append(self._parse_artist(artist))
        return track

    def _parse_artist(self, obj: dict) -> Artist:
        artist = Artist(
            item_id=str(obj["id"]),
            name=obj["name"],
            provider=self.instance_id,
            provider_mappings={
                ProviderMapping(
                    item_id=str(obj["id"]),
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
        )
        if "avatar" in obj:
            artist.metadata.add_image(
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=f"{obj['avatar']}?param=50y50",
                    provider=self.instance_id,
                    remotely_accessible=True,
                )
            )
        return artist

    def _parse_album(self, obj: dict) -> Album:
        album = Album(
            item_id=str(obj["id"]),
            provider=self.instance_id,
            name=obj["name"],
            provider_mappings={
                ProviderMapping(
                    item_id=obj["id"],
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
        )
        if "picUrl" in obj:
            album.metadata.add_image(
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=obj["picUrl"],
                    provider=self.instance_id,
                    remotely_accessible=True,
                )
            )
        return album

    def _parse_playlist(self, obj: dict) -> Playlist:
        playlist = Playlist(
            item_id=str(obj["id"]),
            provider=self.instance_id,
            name=obj["name"],
            provider_mappings={
                ProviderMapping(
                    item_id=obj["id"],
                    provider_domain=self.domain,
                    provider_instance=self.instance_id,
                    available=True,
                )
            },
        )
        if "coverImgUrl" in obj:
            playlist.metadata.add_image(
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=obj["coverImgUrl"],
                    provider=self.instance_id,
                    remotely_accessible=True,
                )
            )
        if "picUrl" in obj:
            playlist.metadata.add_image(
                MediaItemImage(
                    type=ImageType.THUMB,
                    path=obj["picUrl"],
                    provider=self.instance_id,
                    remotely_accessible=True,
                )
            )
        return playlist
