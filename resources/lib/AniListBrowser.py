# -*- coding: utf-8 -*-

from __future__ import absolute_import
from builtins import filter
from builtins import map
from builtins import str
from builtins import range
from builtins import object
import itertools
import requests
import json
import time
import datetime
import ast
import pickle
import xbmc
from functools import partial
from .ui.globals import g
from .ui import database
from .ui.divide_flavors import div_flavor
from resources.lib.database.cache import use_cache
from resources.lib.database.anilist_sync import shows
from resources.lib.modules.list_builder import ListBuilder

class AniListBrowser(object):
    _URL = "https://graphql.anilist.co"

    def __init__(self, title_key=None):
        if title_key:
            self._TITLE_LANG = self._title_lang(title_key)
        else:
            self._TITLE_LANG = "userPreferred"
        self.shows_database = shows.AnilistSyncDatabase()
        self.anime_list_key = ('data', 'Page', 'media')
        self.list_builder = ListBuilder()

    def _title_lang(self, title_key):
        title_lang = {
            "40370": "userPreferred",
            "Romaji (Shingeki no Kyojin)": "userPreferred",
            "40371": "english",
            "English (Attack on Titan)": "english"
            }

        return title_lang[title_key]

    def _handle_paging(self, hasNextPage, base_url, page):
        if not hasNextPage:
            return []

        next_page = page + 1
        name = "Next Page (%d)" %(next_page)
        return [g.allocate_item(name, base_url % next_page, True, None)]

    def get_popular(self, page=1, format_in=''):
        # using https://manga.tokyo/columns/what-is-a-cour-and-a-season-in-anime/ to define seasons

        # Get current season
        year = datetime.date.today().year
        month = datetime.date.today().month
        season = ''
        if month <= 3:
            season = 'WINTER'
        elif month <= 6:
            season = 'SPRING'
        elif month <= 9:
            season = 'SUMMER'
        elif month <= 12:
            season = 'FALL'

        variables = {
            'page': g.PAGE,
            'type': "ANIME",
            'season': season,
            'year': str(year) + '%',
            'sort': "POPULARITY_DESC"
            }

        if g.get_bool_setting("general.menus"):
            variables['page'] = page

        if format_in:
            variables['format'] = [format_in.upper()]

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/list", variables=variables, dict_key=self.anime_list_key, page=page, cached=1
            )
        if g.get_bool_setting("general.menus"):
            popular = database.get(self.get_base_res, 0.125, variables, page)
            return self._process_anilist_view(popular, "anilist_popular/%d", page)
        else:
            self.list_builder.show_list_builder(anilist_list)

    def get_trending(self, page=1, format_in=''):
        variables = {
            'page': g.PAGE,
            'type': "ANIME",
            'sort': ["TRENDING_DESC"]
            }

        if g.get_bool_setting("general.menus"):
            variables['page'] = page

        if format_in:
            variables['format'] = [format_in.upper()]

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/list", variables=variables, dict_key=self.anime_list_key, page=page,
            cached=1
        )

        if g.get_bool_setting("general.menus"):
            trending = database.get(self.get_base_res, 0.125, variables, page)
            return self._process_anilist_view(trending, "anilist_trending/%d", page)
        else:
            self.list_builder.show_list_builder(anilist_list)

    def get_upcoming(self, page=1, format_in=''):
        # using https://manga.tokyo/columns/what-is-a-cour-and-a-season-in-anime/ to define seasons

        # Get next season
        year = datetime.date.today().year
        month = datetime.date.today().month
        if month <= 9:
            next_month = month+3
        else:
            next_month = 1

        season = ''
        if next_month <= 3:
            season = 'WINTER'
        elif next_month <= 6:
            season = 'SPRING'
        elif next_month <= 9:
            season = 'SUMMER'
        elif next_month <= 12:
            season = 'FALL'

        if g.get_bool_setting("general.menus"):
            variables = {
                'page': page,
                'type': "ANIME",
                'season': season,
                'year': str(year) + '%',
                'sort': "POPULARITY_DESC"
            }
        else:
            variables = {
                'page': g.PAGE,
                'type': "ANIME",
                'season': season,
                'seasonYear': year
            }

        if format_in:
            variables['format'] = [format_in.upper()]

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/list", variables=variables, dict_key=self.anime_list_key, page=page, cached=1
            )

        if g.get_bool_setting("general.menus"):
            upcoming = database.get(self.get_base_res, 0.125, variables, page)
            return self._process_anilist_view(upcoming, "anilist_upcoming/%d", page)
        else:
            self.list_builder.show_list_builder(anilist_list)

    def get_all_time_popular(self, page=1, format_in=''):
        variables = {
            'page': g.PAGE,
            'type': "ANIME",
            'sort': "POPULARITY_DESC"
            }

        if g.get_bool_setting("general.menus"):
            variables['page'] = page

        if format_in:
            variables['format'] = [format_in.upper()]

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/list", variables=variables, dict_key=self.anime_list_key, page=page, cached=1
            )

        if g.get_bool_setting("general.menus"):
            all_time_popular = database.get(self.get_base_res, 0.125, variables, page)
            return self._process_anilist_view(all_time_popular, "anilist_all_time_popular/%d", page)
        else:
            self.list_builder.show_list_builder(anilist_list)

    @use_cache()
    def get_airing(self, page=1, format_in=''):
        # airing = database.get(self._get_airing, 12, page, format_in)
        # return airing
        return self._get_airing(page, format_in)

    def _get_airing(self, page=1, format_in=''):
        today = datetime.date.today()
        today_ts = int(time.mktime(today.timetuple()))
        weekStart = today_ts - 86400
        weekEnd = today_ts + (86400*6)

        variables = {
            'weekStart': weekStart,
            'weekEnd': weekEnd,
            'page': page
            }

        if format_in:
            variables['format'] = [format_in.upper()]

        list_ = []

        for i in range(0, 4):
            popular = self.get_airing_res(variables, page)
            list_.append(popular)

            if not popular['pageInfo']['hasNextPage']:
                break

            page += 1
            variables['page'] = page
  
        results = list(map(self._process_airing_view, list_))
        results = list(itertools.chain(*results))
        return results

    def get_search(self, query, page=1):
        variables = {
            'page': g.PAGE,
            'search': query,
            'sort': "SEARCH_MATCH",
            'type': "ANIME"
            }

        if g.get_bool_setting("general.menus"):
            variables['page'] = page

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime", variables=variables, dict_key=self.anime_list_key, page=page, cached=1
            )

        if g.get_bool_setting("general.menus"):
            search = database.get(self.get_search_res, 0.125, variables, page)
            return self._process_anilist_view(search, "search/%s/%%d" % query, page)
        else:
            self.list_builder.show_list_builder(anilist_list)

    def get_recommendation(self, anilist_id, page=1):
        variables = {
            'page': g.PAGE,
            'id': anilist_id
            }

        if g.get_bool_setting("general.menus"):
            variables['page'] = page

        dict_key = ('data', 'Media', 'recommendations', 'nodes')

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/recommendations", variables=variables, dict_key=dict_key, page=page, cached=1
            )
        #recommendation = database.get(self.get_recommendations_res, 0.125, variables, page)
        #return self._process_recommendation_view(recommendation, "anichart_popular/%d", page)
        self.list_builder.show_list_builder(anilist_list)

    def get_anilist(self, mal_id):
        variables = {
            'id': mal_id,
            'type': "ANIME"
            }

        mal_to_anilist = self.get_anilist_res(variables)
        return self._process_mal_to_anilist(mal_to_anilist)

    def get_mal_to_anilist(self, mal_id):
        variables = {
            'id': mal_id,
            'type': "ANIME"
            }

        mal_to_anilist = self.get_mal_to_anilist_res(variables)
        return self._process_mal_to_anilist(mal_to_anilist)
        
    def get_airing_res(self, variables, page=1):
        query = '''
        query (
                $weekStart: Int,
                $weekEnd: Int,
                $page: Int,
        ){
                Page(page: $page) {
                        pageInfo {
                                hasNextPage
                                total
                        }
                        airingSchedules(
                                airingAt_greater: $weekStart
                                airingAt_lesser: $weekEnd
                        ) {
                                id
                                episode
                                airingAt
                                media {
                                        
        id
        idMal
        title {
                romaji
                userPreferred
                english
        }
        description
        genres
        averageScore
        isAdult
        rankings {
                rank
                type
                season
        }
        coverImage {
                extraLarge
        }
                                }
                        }
                }
        }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Page']
        return json_res

    def get_base_res(self, variables, page=1):
        query = '''
        query (
            $page: Int = 1,
            $type: MediaType,
            $isAdult: Boolean = false,
            $format:[MediaFormat],
            $season: MediaSeason,
            $year: String,
            $sort: [MediaSort] = [POPULARITY_DESC, SCORE_DESC]
        ) {
            Page (page: $page, perPage: 20) {
                pageInfo {
                    hasNextPage
                }
                ANIME: media (
                    format_in: $format,
                    type: $type,
                    season: $season,
                    startDate_like: $year,
                    sort: $sort,
                    isAdult: $isAdult
                ) {
                    id
                    idMal
                    title {
                        userPreferred,
                        romaji,
                        english
                    }
                    coverImage {
                        extraLarge
                    }
                    startDate {
                        year,
                        month,
                        day
                    }
                    description
                    synonyms
                    format
                    episodes
                    status
                    genres
                    duration
                }
            }
        }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Page']
        return json_res

    def anime_list_query(self):
        query = '''
        query (
            $page: Int = 1,
            $type: MediaType,
            $isAdult: Boolean = false,
            $format:[MediaFormat],
            $season: MediaSeason,
            $year: String,
            $sort: [MediaSort] = [POPULARITY_DESC, SCORE_DESC]
        ) {
            Page (page: $page, perPage: 20) {
                pageInfo {
                    hasNextPage
                    lastPage
                }
                ANIME: media (
                    format_in: $format,
                    type: $type,
                    season: $season,
                    startDate_like: $year,
                    sort: $sort,
                    isAdult: $isAdult
                ) {
                    id
                    idMal
                    title {
                        userPreferred,
                        romaji,
                        english
                    }
                    coverImage {
                        extraLarge
                    }
                    startDate {
                        year,
                        month,
                        day
                    }
                    description
                    synonyms
                    format
                    episodes
                    status
                    genres
                    duration
                }
            }
        }
        '''

        return query

    def get_search_res(self, variables, page=1):
        query = '''
        query (
            $page: Int = 1,
            $type: MediaType,
            $isAdult: Boolean = false,
            $search: String,
            $sort: [MediaSort] = [SCORE_DESC, POPULARITY_DESC]
        ) {
            Page (page: $page, perPage: 20) {
                pageInfo {
                    hasNextPage
                }
                ANIME: media (
                    type: $type,
                    search: $search,
                    sort: $sort,
                    isAdult: $isAdult
                ) {
                    id
                    idMal
                    title {
                        userPreferred,
                        romaji,
                        english
                    }
                    coverImage {
                        extraLarge
                    }
                    startDate {
                        year,
                        month,
                        day
                    }
                    description
                    synonyms
                    format
                    episodes
                    status
                    genres
                    duration
                }
            }
        }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Page']
        return json_res

    def get_recommendations_res(self, variables, page=1):
        query = '''
        query media($id:Int,$page:Int){Media(id:$id) {
            id
            recommendations (page:$page, perPage: 20, sort:[RATING_DESC,ID]) {
                pageInfo {
                    hasNextPage
                }
                nodes {
                    mediaRecommendation {
                        id
                        idMal
                        title {
                            userPreferred,
                            romaji,
                            english
                        }
                        format
                        type
                        status
                        coverImage {
                            extraLarge
                        }
                        startDate {
                            year,
                            month,
                            day
                        }
                        description
                        duration
                        genres
                        synonyms
                        episodes
                    }
                }
            }
        }
                                       }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Media']['recommendations']
        return json_res

    def get_anilist_res(self, variables):
        query = '''
        query($id: Int, $type: MediaType){Media(id: $id, type: $type) {
            id
            idMal
            title {
                userPreferred,
                romaji,
                english
            }
            coverImage {
                extraLarge
            }
            startDate {
                year,
                month,
                day
            }
            description
            synonyms
            format
            episodes
            status
            genres
            duration
            }
        }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Media']
        return json_res 

    def get_mal_to_anilist_res(self, variables):
        query = '''
        query($id: Int, $type: MediaType){Media(idMal: $id, type: $type) {
            id
            idMal
            title {
                userPreferred,
                romaji,
                english
            }
            coverImage {
                extraLarge
            }
            startDate {
                year,
                month,
                day
            }
            description
            synonyms
            format
            episodes
            status
            genres
            duration
            }
        }
        '''

        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        json_res = results['data']['Media'] 
        return json_res  

    @div_flavor
    def _process_anilist_view(self, json_res, base_plugin_url, page, dub=False):
        hasNextPage = json_res['pageInfo']['hasNextPage']

        if dub:
            mapfunc = partial(self._base_anilist_view, mal_dub=dub)
        else:
            mapfunc = self._base_anilist_view

        all_results = list(map(mapfunc, json_res['ANIME']))
        all_results = list(itertools.chain(*all_results))

        all_results += self._handle_paging(hasNextPage, base_plugin_url, page)
        return all_results

    def _process_airing_view(self, json_res):
        filter_json = [x for x in json_res['airingSchedules'] if x['media']['isAdult'] == False]
        ts = int(time.time())
        mapfunc = partial(self._base_airing_view, ts=ts)
        all_results = list(map(mapfunc, filter_json))
        return all_results

    @div_flavor
    def _process_recommendation_view(self, json_res, base_plugin_url, page, dub=False):
        hasNextPage = json_res['pageInfo']['hasNextPage']
        res = [i['mediaRecommendation'] for i in json_res['nodes']]

        if dub:
            mapfunc = partial(self._base_anilist_view, mal_dub=dub)
        else:
            mapfunc = self._base_anilist_view

        all_results = list(map(mapfunc, res))
        all_results = list(itertools.chain(*all_results))

        all_results += self._handle_paging(hasNextPage, base_plugin_url, page)
        return all_results

    def _process_mal_to_anilist(self, res):
        self._database_update_show(res)

        return  database.get_show(str(res['id']))

    def _base_anilist_view(self, res, mal_dub=None):
        in_database = database.get_show(str(res['id']))

        if not in_database:
            self._database_update_show(res)
            kodi_meta = None
        else:
            kodi_meta = in_database['info']
            if kodi_meta:
                kodi_meta = pickle.loads(kodi_meta)
        #remove cached eps for releasing shows every five days so new eps metadata can be shown
        if res.get('status') == 'RELEASING':
            try:
                from datetime import datetime, timedelta
                present = datetime.now()
                last_updated = database.get_episode_list(res['id'])[0]['last_updated']
                last_updated = datetime.strptime(last_updated, '%Y-%m-%d')
                if last_updated.date() <= present.date():
                    database.remove_episodes(res['id'])
            except:
                pass

        title = res['title'][self._TITLE_LANG]
        if not title:
            title = res['title']['userPreferred']

        info = {}

        try:
            info['genre'] = res.get('genres')
        except:
            pass

        try:
            info['plot'] = res['description'].replace('<i>', '[I]').replace('</i>', '[/I]').replace('<br>', '[CR]')
        except:
            pass

        try:
            info['title'] = title
        except:
            pass

        try:
            info['duration'] = res.get('duration') * 60
        except:
            pass

        try:
            start_date = res.get('startDate')
            info['aired'] = '{}-{:02}-{:02}'.format(start_date['year'], start_date['month'], start_date['day'])
        except:
            pass

        try:
            info['status'] = res.get('status')
        except:
            pass

        info['mediatype'] = 'tvshow'

        dub = False
        mal_id = str(res.get('idMal', 0))
        if mal_dub and mal_dub.get(mal_id):
            dub = True

        base = {
            "name": title,
            "url": "animes/%s/%s/" % (res['id'], res.get('idMal')),
            "image": res['coverImage']['extraLarge'],
            "info": info
        }
        if kodi_meta:
            base["fanart"] = kodi_meta.get('fanart', res['coverImage']['extraLarge'])

        if res['format'] == 'MOVIE' and res['episodes'] == 1:
            base['url'] = "play_movie/%s/1/" % (res['id'])
            base['info']['mediatype'] = 'movie'
            return self._parse_view(base, False, dub=dub, is_playable=True)

        return self._parse_view(base, dub=dub)

    def _base_airing_view(self, res, ts):
        airingAt = datetime.datetime.fromtimestamp(res['airingAt'])
        airingAt_day = airingAt.strftime('%A')
        airingAt_time = airingAt.strftime('%I:%M %p')
        airing_status = 'airing' if res['airingAt'] > ts else 'aired'
        rank = None
        rankings = res['media']['rankings']
        if rankings and rankings[-1]['season']:
            rank = rankings[-1]['rank']
        genres = res['media']['genres']
        if genres:
            genres = ' | '.join(genres[:3])
        title = res['media']['title'][self._TITLE_LANG]
        if not title:
            title = res['media']['title']['userPreferred']

        base = {
            'release_title': title,
            'poster': res['media']['coverImage']['extraLarge'],
            'ep_title': '{} {} {}'.format(res['episode'], airing_status, airingAt_day),
            'ep_airingAt': airingAt_time,
            'averageScore': res['media']['averageScore'],
            'rank': rank,
            'plot': res['media']['description'],
            'genres': genres,
            'id': res['media']['id']
            }
            
        return base

    def _database_update_show(self, res):
        titles = self._get_titles(res)
        start_date = self._get_start_date(res)
        title_userPreferred = res['title'][self._TITLE_LANG]
        if not title_userPreferred:
            title_userPreferred = res['title']['userPreferred']

        kodi_meta = {}
        kodi_meta['name'] = res['title']['userPreferred']
        kodi_meta['title_userPreferred'] = title_userPreferred
        kodi_meta['start_date'] = start_date
        kodi_meta['query'] = titles
        kodi_meta['episodes'] = res['episodes']
        kodi_meta['poster'] = res['coverImage']['extraLarge']
        kodi_meta['status'] = res.get('status')
        
        database._update_show(
            res['id'],
            str(kodi_meta)
            )

    def _get_titles(self, res):
        titles = list(set(res['title'].values()))
        if res['format'] == 'MOVIE':
            titles = list(res['title'].values())
        titles = list(map(lambda x: x.encode('ascii','ignore').decode("utf-8") if x else [], titles))[:3]
        query_titles = '({})'.format(')|('.join(map(str, titles)))
        return query_titles

    def _get_start_date(self, res):
        try:
            start_date = res.get('startDate')
            start_date = '{}-{:02}-{:02}'.format(start_date['year'], start_date['month'], start_date['day'])
        except:
            start_date = 'null'

        return start_date

    def _parse_view(self, base, is_dir=True, dub=False, is_playable=False):
        if dub:
            return self._parse_div_view(base, is_dir, is_playable)

        return [
            g.allocate_item("%s" % base["name"],
                                base["url"],
                                is_dir,
                                base["image"],
                                base["info"],
                                base.get("fanart", None),
                                base["image"],
                                is_playable)
            ]

    def _parse_div_view(self, base, is_dir, is_playable):
        parsed_view = [
            g.allocate_item("%s" % base["name"],
                                base["url"] + '2',
                                is_dir,
                                base["image"],
                                base["info"],
                                base.get("fanart", None),
                                base["image"],
                                is_playable)
            ]

        parsed_view.append(
            g.allocate_item("%s (Dub)" % base["name"],
                                base["url"] + '0',
                                is_dir,
                                base["image"],
                                base["info"],
                                base.get("fanart", None),
                                base["image"])
            )

        return parsed_view

    def get_genres(self):
        query = '''
        query {
            genres: GenreCollection,
            tags: MediaTagCollection {
                name
                isAdult
            }
        }
        '''

        result = requests.post(self._URL, json={'query': query})
        results = result.json()['data']
        genres_list = results['genres']

        del genres_list[6]

        tags_list = []
        tags = [x for x in results['tags'] if x['isAdult'] == False]
        for tag in tags:
            tags_list.append(tag['name'])

        genre_display_list = genres_list + tags_list

        g.add_directory_item(
            'Multi Select...', 
            action="anilist_genres_page",
            action_args= {
                'genres_tags': genre_display_list,
                },
            mediatype="tvshow",
            is_folder=False,
            )
        genres = genre_display_list

        if genres is None:
            g.cancel_directory()
            return

        for i in genres:
            if i in genres_list:
                action_args = {'genres': [i]}
            else:
                action_args = {'tags': [i]}

            g.add_directory_item(
                i, action="anilist_genres_page", action_args=action_args
                )
        g.close_directory(g.CONTENT_GENRES)

        # return self._select_genres(genre_dialog, genre_display_list)

    def select_genres(self, genre_dialog, genre_display_list):
        genre_list = []
        tag_list = []

        if 'genres_tags' in genre_display_list:
            genres_tags = genre_display_list.get('genres_tags')
            multiselect = genre_dialog(genres_tags)

            if not multiselect:
                return

            for selection in multiselect:
                if selection <= 17:
                    genre_list.append(genres_tags[selection])
                    continue

                tag_list.append(genres_tags[selection])

            g.REQUEST_PARAMS.pop('action_args')
            g.REQUEST_PARAMS['action_args'] = {
                'genres': genre_list,
                'tags': tag_list
            }

            g.container_update(replace=True)
        else:
            if 'genres' in genre_display_list:
                genre_list = genre_display_list['genres']
            else:
                tag_list = genre_display_list['tags']

        return self._genres_payload(genre_list, tag_list)

    def _genres_payload (self, genre_list, tag_list, page=1):
        query = '''
        query (
            $page: Int,
            $type: MediaType,
            $isAdult: Boolean = false,
            $includedGenres: [String],
            $includedTags: [String],
            $sort: [MediaSort] = [SCORE_DESC, POPULARITY_DESC]
        ) {
            Page (page: $page, perPage: 20) {
                pageInfo {
                    hasNextPage
                }
                ANIME: media (
                    type: $type,
                    genre_in: $includedGenres,
                    tag_in: $includedTags,
                    sort: $sort,
                    isAdult: $isAdult
                ) {
                    id
                    idMal
                    title {
                        userPreferred,
                        romaji,
                        english
                    }
                    coverImage {
                        extraLarge
                    }
                    startDate {
                        year,
                        month,
                        day
                    }
                    description
                    synonyms
                    format
                    episodes
                    status
                    genres
                    duration
                    isAdult
                    }
                }
            }
        '''

        variables = {
            'page': g.PAGE,
            'type': "ANIME"
            }

        if genre_list:
            variables["genres"] = genre_list

        if tag_list:
            variables["tags"] = tag_list

        anilist_list = self.shows_database.extract_trakt_page(
            self._URL, query_path="search/anime/genre", variables=variables, dict_key=self.anime_list_key, page=page, cached=1
            )

        self.list_builder.show_list_builder(anilist_list)
        # return self._process_genre_view(query, variables, "anilist_genres/%s/%s/%%d" %(genre_list, tag_list), page)

    @div_flavor
    def _process_genre_view(self, query, variables, base_plugin_url, page, dub=False):
        result = requests.post(self._URL, json={'query': query, 'variables': variables})
        results = result.json()

        if "errors" in results:
            return

        anime_res = results['data']['Page']['ANIME']
        hasNextPage = results['data']['Page']['pageInfo']['hasNextPage']

        if dub:
            mapfunc = partial(self._base_anilist_view, mal_dub=dub)
        else:
            mapfunc = self._base_anilist_view

        all_results = list(map(mapfunc, anime_res))
        all_results = list(itertools.chain(*all_results))

        all_results += self._handle_paging(hasNextPage, base_plugin_url, page)
        return all_results

    def get_genres_page(self, genre_string, tag_string, page):
        return self._genres_payload(ast.literal_eval(genre_string), ast.literal_eval(tag_string), page)
