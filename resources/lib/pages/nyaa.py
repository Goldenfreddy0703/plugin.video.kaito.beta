# -*- coding: utf-8 -*-
from builtins import str
from builtins import map
from builtins import filter
from builtins import object
import json
import bs4 as bs
import re
from functools import partial
from ..ui import utils, source_utils, control
from resources.lib.ui.globals import g
from ..ui.BrowserBase import BrowserBase
from ..debrid import real_debrid, all_debrid, premiumize
from ..ui import database
import requests
import threading
import copy
import ast
import itertools
from resources.lib.database.cache import use_cache
from resources.lib.database.anilist_sync import shows
from resources.lib.third_party import anitopy

class sources(BrowserBase):
    def _parse_anime_view(self, res):
        info = {}
        name = res['name']
        image = None
        info['title'] = name
        info['mediatype'] = 'episode'


        art = {
            'poster': image,
            'fanart': image,
            'keyart': image,
        }

        menu_item = {
            'art': art,
            'info': info
        }

        g.add_directory_item(
            name,
            action='play_latest',
            action_args={"debrid_provider": res['debrid_provider'], "hash": res['hash'], "mediatype": "episode"},
            menu_item=menu_item,
            is_playable=True
        )
        # return g.allocate_item(name, "play_latest/" + str(url), False, image, info, is_playable=True)

    def _parse_nyaa_episode_view(self, res, episode):
        source = {
            'release_title': control.decode_py2(res['name']),
            'hash': res['hash'],
            'type': 'torrent',
            'quality': self.get_quality(res['name']),
            'debrid_provider': res['debrid_provider'],
            'provider': 'nyaa',
            'episode_re': episode,
            'size': res['size'],
            'info': source_utils.getInfo(res['name']),
            'lang': source_utils.getAudio_lang(res['name'])
            }

        return source

    def _parse_nyaa_cached_episode_view(self, res, episode):
        source = {
            'release_title': control.decode_py2(res['name']),
            'hash': res['hash'],
            'type': 'torrent',
            'quality': self.get_quality(res['name']),
            'debrid_provider': res['debrid_provider'],
            'provider': 'nyaa (Local Cache)',
            'episode_re': episode,
            'size': res['size'],
            'info': source_utils.getInfo(res['name']),
            'lang': source_utils.getAudio_lang(res['name'])
            }

        return source

    def get_quality(self, release_title):
        release_title = release_title.lower()
        quality = 'NA'
        if '4k' in release_title:
            quality = '4K'
        if '2160' in release_title:
            quality = '4K'
        if '1080' in release_title:
            quality = '1080p'
        if '720' in release_title:
            quality = '720p'
        if '480' in release_title:
            quality = 'NA'

        return quality

    def _handle_paging(self, total_pages, base_url, page):
        if page == total_pages:
            return []

        next_page = page + 1
        name = "Next Page (%d/%d)" % (next_page, total_pages)
        return [utils.allocate_item(name, base_url % next_page, True, None)]

    def _json_request(self, url, data=''):
        response = json.loads(self._get_request(url, data))
        return response
    
    @use_cache(0.125)
    def __get_request(self, url):
        json_resp = self._get_request(url)
        return json_resp

    def _process_anime_view(self, url, data, base_plugin_url, page):
        json_resp = self.__get_request(url)
        results = bs.BeautifulSoup(json_resp, 'html.parser')
        rex = r'(magnet:)+[^"]*'
        search_results = [
            (i.find_all('a',{'href':re.compile(rex)})[0].get('href'),
            i.find_all('a', {'class': None})[1].get('title'))
            for i in results.select("tr.default,tr.success")
            ]

        list_ = [
            {'magnet': magnet,
             'name': name
             }
            for magnet,name in search_results]

        for torrent in list_:
            torrent['hash'] = re.findall(r'btih:(.*?)(?:&|$)', torrent['magnet'])[0]

        cache_list = TorrentCacheCheck().torrentCacheCheck(list_)
        all_results = list(map(self._parse_anime_view, cache_list))
        g.close_directory(g.CONTENT_EPISODE)

        #return all_results

    # Some sort of processing after getting a list of sources...
    def _process_nyaa_episodes(self, url, episode, season=None):
        json_resp = requests.get(url).text
        results = bs.BeautifulSoup(json_resp, 'html.parser')
        rex = r'(magnet:)+[^"]*'
        search_results = [
            (i.find_all('a',{'href':re.compile(rex)})[0].get('href'),
             i.find_all('a', {'class': None})[1].get('title'),
             i.find_all('td', {'class': 'text-center'})[1].text,
             i.find_all('td', {'class': 'text-center'})[-1].text)
            for i in results.select("tr.danger,tr.default,tr.success")
            ]

        list_ = [
            {'magnet': magnet,
             'name': name,
             'size': size.replace('i', ''),
             'downloads': int(downloads)
             }
            for magnet,name,size,downloads in search_results]

        regex = r'\ss(\d+)|season\s(\d+)|(\d+)+(?:st|[nr]d|th)\sseason'
        regex_ep = r'\de(\d+)\b|\se(\d+)\b|\s-\s(\d{1,3})\b'
        rex = re.compile(regex)
        rex_ep = re.compile(regex_ep)

        filtered_list = []

        for idx, torrent in enumerate(list_):
            torrent['hash'] = re.findall(r'btih:(.*?)(?:&|$)', torrent['magnet'])[0]
            
            parsed = anitopy.parse(torrent['name'])
            anime_season = parsed.get("anime_season")
            episode_number = parsed.get("episode_number", 0)

            try:
                if isinstance(episode_number, list) or isinstance(anime_season, list):
                    filtered_list.append(torrent)
                    continue

                if season and anime_season:
                    if int(season) != int(anime_season):
                        continue

                if int(episode) == int(episode_number):
                    filtered_list.append(torrent)
                    continue
                if episode_number == 0:
                    filtered_list.append(torrent)
            except:
                filtered_list.append(torrent)

                # title = torrent['name'].lower()

                # ep_match = rex_ep.findall(title)
                # ep_match = list(map(int, list(filter(None, itertools.chain(*ep_match)))))

                # if ep_match and ep_match[0] != int(episode):
                #     regex_ep_range = r'\s\d+-\d+|\s\d+~\d+|\s\d+\s-\s\d+|\s\d+\s~\s\d+'
                #     rex_ep_range = re.compile(regex_ep_range)

                #     if rex_ep_range.search(title):
                #         pass
                #     else:
                #         continue
                
                # match = rex.findall(title)
                # match = list(map(int, list(filter(None, itertools.chain(*match)))))

                # if not match or match[0] == int(season):
                #     filtered_list.append(torrent)

        cache_list = TorrentCacheCheck().torrentCacheCheck(filtered_list)
        cache_list = sorted(cache_list, key=lambda k: k['downloads'], reverse=True)
        mapfunc = partial(self._parse_nyaa_episode_view, episode=episode)
        all_results = list(map(mapfunc, cache_list))
        return all_results

    def _process_nyaa_backup(self, url, anilist_id, _zfill, episode='', rescrape=False, season=None):
        json_resp = requests.get(url).text
        results = bs.BeautifulSoup(json_resp, 'html.parser')
        rex = r'(magnet:)+[^"]*'
        search_results = [
            (i.find_all('a',{'href':re.compile(rex)})[0].get('href'),
             i.find_all('a', {'class': None})[1].get('title'),
             i.find_all('td', {'class': 'text-center'})[1].text,
             i.find_all('td', {'class': 'text-center'})[-1].text)
            for i in results.select("tr.danger,tr.default,tr.success")
            ][:30]

        list_ = [
            {'magnet': magnet,
             'name': name,
             'size': size.replace('i', ''),
             'downloads': int(downloads)
             }
            for magnet,name,size,downloads in search_results]

        filtered_list = []

        for torrent in list_:
            torrent['hash'] = re.findall(r'btih:(.*?)(?:&|$)', torrent['magnet'])[0]
            parsed = anitopy.parse(torrent['name'])
            anime_season = parsed.get("anime_season")
            episode_number = parsed.get("episode_number", '0')

            try:
                if isinstance(episode_number, list):
                    if season:
                        if anime_season:
                            if isinstance(anime_season, list):
                                if season in anime_season:
                                    if episode:
                                        if int(episode) >= int(min(episode_number)) and int(episode) <= int(
                                                max(episode_number)):
                                            filtered_list.append(torrent)
                                            continue
                                        else:
                                            continue
                                    else:
                                        filtered_list.append(torrent)
                                        continue
                                else:
                                    continue
                            elif int(season) == int(anime_season):
                                if episode:
                                    if int(episode) >= int(min(episode_number)) and int(episode) <= int(max(episode_number)):
                                        filtered_list.append(torrent)
                                        continue
                                    else:
                                        continue
                                else:
                                    filtered_list.append(torrent)
                                    continue
                            else:
                                continue
                        else:
                            if episode and episode_number:
                                if int(episode) >= int(min(episode_number)) and int(episode) <= int(max(episode_number)):
                                    filtered_list.append(torrent)
                                    continue
                                else:
                                    continue
                            else:
                                filtered_list.append(torrent)
                                continue
                    else:
                        if episode and episode_number:
                            if int(episode) >= int(min(episode_number)) and int(episode) <= int(max(episode_number)):
                                filtered_list.append(torrent)
                                continue
                            else:
                                continue
                        else:
                            filtered_list.append(torrent)
                            continue
                if season and anime_season:
                    if int(season) > 1:
                        if isinstance(anime_season, list):
                            if season in anime_season:
                                if episode_number and int(episode_number) != 0:
                                    if int(episode) == int(episode_number):
                                        filtered_list.append(torrent)
                                        continue
                                    else:
                                        continue
                                else:
                                    filtered_list.append(torrent)
                                    continue
                            else:
                                continue
                        elif int(season) == int(anime_season):
                            if episode_number and int(episode_number) != 0:
                                if int(episode) == int(episode_number):
                                    filtered_list.append(torrent)
                                    continue
                                else:
                                    continue
                            else:
                                filtered_list.append(torrent)
                                continue
                        else:
                            continue
                    elif int(season) <= 1:
                        if isinstance(anime_season, list):
                            if season in anime_season and episode_number:
                                if int(episode) == int(episode_number) or int(episode_number) == 0:
                                    filtered_list.append(torrent)
                                    continue
                                else:
                                    continue
                            else:
                                continue
                        elif int(anime_season) <= int(season) and episode_number:
                            if int(episode) == int(episode_number) or int(episode_number) == 0:
                                filtered_list.append(torrent)
                                continue
                            else:
                                continue
                        else:
                            continue
                else:
                    if episode_number:
                        if int(episode) == int(episode_number):
                            filtered_list.append(torrent)
                            continue
                if int(episode_number) == 0 :
                    filtered_list.append(torrent)
                    continue
            except:
                filtered_list.append(torrent)
        # if not rescrape:
        #     database.addTorrentList(anilist_id, list_, _zfill)

        cache_list = TorrentCacheCheck().torrentCacheCheck(filtered_list)
        cache_list = sorted(cache_list, key=lambda k: k['downloads'], reverse=True)

        mapfunc = partial(self._parse_nyaa_episode_view, episode=episode)
        all_results = list(map(mapfunc, cache_list))
        # Sort list to put torrents with extras/specials at bottom of list.
        all_results = sorted(all_results, key=lambda x: x['release_title'].lower().find('extra') != -1 or x['release_title'].lower().find('special') != -1 or x['release_title'].lower().find('movie') != -1)
        return all_results

    def _process_nyaa_movie(self, url, episode):
        json_resp = requests.get(url).text
        results = bs.BeautifulSoup(json_resp, 'html.parser')
        rex = r'(magnet:)+[^"]*'
        search_results = [
            (i.find_all('a',{'href':re.compile(rex)})[0].get('href'),
             i.find_all('a', {'class': None})[1].get('title'),
             i.find_all('td', {'class': 'text-center'})[1].text,
             i.find_all('td', {'class': 'text-center'})[-1].text)
            for i in results.select("tr.danger,tr.default,tr.success")
            ]

        list_ = [
            {'magnet': magnet,
             'name': name,
             'size': size.replace('i', ''),
             'downloads': int(downloads)
             }
            for magnet,name,size,downloads in search_results]

        for idx, torrent in enumerate(list_):
            torrent['hash'] = re.findall(r'btih:(.*?)(?:&|$)', torrent['magnet'])[0]

        cache_list = TorrentCacheCheck().torrentCacheCheck(list_)
        cache_list = sorted(cache_list, key=lambda k: k['downloads'], reverse=True)
        mapfunc = partial(self._parse_nyaa_episode_view, episode=episode)
        all_results = list(map(mapfunc, cache_list))
        return all_results

    def _process_cached_sources(self, list_, episode):
        cache_list = TorrentCacheCheck().torrentCacheCheck(list_)
        mapfunc = partial(self._parse_nyaa_cached_episode_view, episode=episode)
        all_results = list(map(mapfunc, cache_list))
        return all_results        

    def get_latest(self, page=1):
        url = "https://nyaa.si/?f=0&c=1_2&q="
        data = ''
        return self._process_anime_view(url, data, "latest/%d", page)

    def get_latest_dub(self, page=1):
        url = "https://nyaa.si/?f=0&c=1_2&q=english+dub"
        data = ''
        return self._process_anime_view(url, data, "latest_dub/%d", page)

    def storeTorrentResults(self, torrent_list):

        try:
            if len(torrent_list) == 0:
                return

            database.addTorrent(self.item_information, torrent_list)
        except:
            pass

    # Method to get sources for shows and movies from nyaa
    def get_sources(self, query, anilist_id, episode, status, media_type, rescrape):
        if media_type == 'movie':
            return self._get_movie_sources(query, anilist_id, episode)

        if anilist_id in {127720}:
            episode += 11
        # Remove any non alphanumeric characters, except for parenthesis. If problems arise with a title that has parenthesis, those can be removed as well and restitch it together.
        # Parenthesis around each name is for searching nyaa and denoting the series name as the important search term.
        tmplist = query.split('|');
        tmpShow = ''
        for i in range(len(tmplist)):
            tmplist[i] = re.sub('[^A-Za-z0-9 ()]', ' ', tmplist[i])
            if ( i == 0 ):
                tmpShow += tmplist[i]
            else:
                tmpShow += '|' + tmplist[i]
        query = tmpShow
        if 'case closed' in query.lower():
            query = '(Detective Conan)'
        sources = self._get_episode_sources(query, anilist_id, episode, status, rescrape)

        if not sources:
            sources = self._get_episode_sources_backup(query, anilist_id, episode)

        return sources

    # Method to get episode sources for shows
    def _get_episode_sources(self, show, anilist_id, episode, status, rescrape):
        if rescrape:
            return self._get_episode_sources_pack(show, anilist_id, episode)
        episode = str(episode)
        # try:
        #     cached_sources, zfill_int = database.getTorrentList(anilist_id)
        #     if cached_sources:
        #         return self._process_cached_sources(cached_sources, episode.zfill(zfill_int))
        # except ValueError:
        #     pass

        # Query... ex 'SPY X FAMILY - 02'
        if 'one piece' in show.lower() or 'detective conan' in show.lower():
            query = '%s "- %s"' % (show, episode.zfill(3))
        else:
            query = '%s "- %s"' % (show, episode.zfill(2))
        # Hard Coded seasons that are weird and have second parts that have their own anilist entry.
        if anilist_id in {113538, 119661, 104578, 116742, 127720}:
            anilist_season = {
                113538: 4,
                119661: 2,
                104578: 3,
                116742: 2,
                110277: 4,
                127720: 1,  
            }
            season = [{"info": {"season": anilist_season[anilist_id]}}]
        else:
            season = shows.AnilistSyncDatabase().get_season_list(anilist_id, None, no_paging=True, smart_play=True)
        if season:
            if 'one piece' in show.lower() or 'detective conan' in show.lower():
                season = str(season[0]["info"]['season']).zfill(3)
                query += '|"S%sE%s "' % (season, episode.zfill(3))
                query += '|"S%s - %s "' % (season[1], episode.zfill(3))
                query += '|"S%s - %s "' % (season[1], episode)
            else:
                season = str(season[0]["info"]['season']).zfill(2)
                query += '|"S%sE%s "' %(season, episode.zfill(2))
                query += '|"S%s - %s "' %(season[1], episode.zfill(2))
                query += '|"S%s - %s "' %(season[1], episode)

        url = "https://nyaa.si/?f=0&c=1_2&q=%s&s=downloads&o=desc" % query            

        if 'one piece' in show.lower() or 'detective conan' in show.lower():
            ret = self._process_nyaa_episodes(url, episode.zfill(3), season) + self._get_episode_sources_pack(show, anilist_id, episode, season)
            ret = [x for x in ret if not (x['release_title'].lower().find('movie') != -1 and x['release_title'].lower().find('+ movie') == -1)]
            return ret
        if status == 'FINISHED':
            return self._get_episode_sources_pack(show, anilist_id, episode, season)

        return self._process_nyaa_episodes(url, episode.zfill(2), season)

    def _get_episode_sources_backup(self, db_query, anilist_id, episode):
        show = requests.get("https://kaito-title.firebaseio.com/%s.json" % anilist_id).json()

        if not show:
            return []

        episode = str(episode)

        if 'general_title' in show:
            query = control.decode_py2(show['general_title'])
            _zfill = show.get('zfill', 2)
            episode = episode.zfill(_zfill)
            query = requests.utils.quote(query)
            url = "https://nyaa.si/?f=0&c=1_2&q=%s&s=downloads&o=desc" % query
            return self._process_nyaa_backup(url, anilist_id, _zfill, episode)

        # try:
        #     kodi_meta = ast.literal_eval(database.get_show(anilist_id)['kodi_meta'])
        #     kodi_meta['query'] = db_query + '|{}'.format(show)
        #     database.update_kodi_meta(anilist_id, kodi_meta)
        # except:
        #     pass

        if 'one piece' in show.lower() or 'detective conan' in show.lower():
            query = '%s "- %s"' % (control.decode_py2(show), episode.zfill(3))
        else:
            query = '%s "- %s"' % (control.decode_py2(show), episode.zfill(2))
        if anilist_id in {113538, 119661, 104578, 116742, 127720}:
            anilist_season = {
                113538: 4,
                119661: 2,
                104578: 3,
                116742: 2,
                110277: 4,
                127720: 1,
            }
            season = [{"info": {"season": anilist_season[anilist_id]}}]
        else:
            season = shows.AnilistSyncDatabase().get_season_list(anilist_id, None, no_paging=True, smart_play=True)
        if season:
            if 'one piece' in show.lower() or 'detective conan' in show.lower():
                season = str(season[0]['info']['season']).zfill(3)
                query += '|"S%sE%s"' % (season, episode.zfill(3))
            else:
                season = str(season[0]['info']['season']).zfill(2)
                query += '|"S%sE%s"' %(season, episode.zfill(2))

        url = "https://nyaa.si/?f=0&c=1_2&q=%s" % query
        return self._process_nyaa_episodes(url, episode, season)

    def _get_episode_sources_pack(self, show, anilist_id, episode, season):
        query = '%s "Batch"|"Complete Series"' % (show)
        query += '|"Bluray"'

        item_information = control.get_item_information(anilist_id)
        episodes = item_information["episode_count"]
        if episodes:
            if 'one piece' in show.lower() or 'detective conan' in show.lower():
                query += '|"001-{0}"|"001~{0}"|"001 - {0}"|"001 ~ {0}"'.format(episodes)
            else:
                query += '|"01-{0}"|"01~{0}"|"01 - {0}"|"01 ~ {0}"'.format(episodes)

        if season:
            query += '|"S{0}"|"Season {0}"'.format(season)
            query += '|"S{0}"|"Season {0}"'.format(str(season).zfill(2))
            #query += '|"S%sE%s"' %(season, episode.zfill(2))

        url = "https://nyaa.si/?f=0&c=1_2&q=%s&s=seeders&&o=desc" % query
        return self._process_nyaa_backup(url, anilist_id, 2, episode.zfill(2), True, season)

    def _get_movie_sources(self, query, anilist_id, episode):
        query = requests.utils.quote(query)
        url = "https://nyaa.si/?f=0&c=1_2&q=%s&s=downloads&o=desc" % query
        sources = self._process_nyaa_movie(url, '1')

        if not sources:
            sources = self._get_movie_sources_backup(anilist_id)

        return sources

    def _get_movie_sources_backup(self, anilist_id, episode='1'):
        show = requests.get("https://kimetsu-title.firebaseio.com/%s.json" % anilist_id).json()

        if not show:
            return []

        if 'general_title' in show:
            query = show['general_title']
            query = requests.utils.quote(query)
            url = "https://nyaa.si/?f=0&c=1_2&q=%s&s=downloads&o=desc" % query
            return self._process_nyaa_backup(url, episode)
        
        query = requests.utils.quote(show)
        url = "https://nyaa.si/?f=0&c=1_2&q=%s" % query
        return self._process_nyaa_movie(url, episode)

class TorrentCacheCheck(object):
    def __init__(self):
        self.premiumizeCached = []
        self.realdebridCached = []
        self.all_debridCached = []
        self.threads = []

        self.episodeStrings = None
        self.seasonStrings = None

    def torrentCacheCheck(self, torrent_list):
        from ..ui.globals import g

        if g.real_debrid_enabled():
            self.threads.append(
                threading.Thread(target=self.realdebridWorker, args=(copy.deepcopy(torrent_list),)))

        if g.premiumize_enabled():
            self.threads.append(threading.Thread(target=self.premiumizeWorker, args=(copy.deepcopy(torrent_list),)))

        if g.all_debrid_enabled():
            self.threads.append(
                threading.Thread(target=self.all_debrid_worker, args=(copy.deepcopy(torrent_list),)))

        for i in self.threads:
            i.start()
        for i in self.threads:
            i.join()

        cachedList = self.realdebridCached + self.premiumizeCached + self.all_debridCached
        return cachedList

    def all_debrid_worker(self, torrent_list):

        api = all_debrid.AllDebrid()

        if len(torrent_list) == 0:
            return

        cache_check = api.check_hash([i['hash'] for i in torrent_list])

        if not cache_check:
            return

        cache_list = []

        for idx, i in enumerate(torrent_list):
            if cache_check['magnets'][idx]['instant'] is True:
                i['debrid_provider'] = 'all_debrid'
                cache_list.append(i)

        self.all_debridCached = cache_list

    def realdebridWorker(self, torrent_list):
        cache_list = []

        hash_list = [i['hash'] for i in torrent_list]

        if len(hash_list) == 0:
            return
        api = real_debrid.RealDebrid()
        realDebridCache = api.checkHash(hash_list)

        for i in torrent_list:
            try:
                if 'rd' not in realDebridCache.get(i['hash'], {}):
                    continue
                if len(realDebridCache[i['hash']]['rd']) >= 1:
                    i['debrid_provider'] = 'real_debrid'
                    cache_list.append(i)
                else:
                    pass
            except KeyError:
                pass

        self.realdebridCached = cache_list

    def premiumizeWorker(self, torrent_list):
        hash_list = [i['hash'] for i in torrent_list]
        if len(hash_list) == 0:
            return
        premiumizeCache = premiumize.Premiumize().hash_check(hash_list)
        premiumizeCache = premiumizeCache['response']
        cache_list = []
        count = 0
        for i in torrent_list:
            if premiumizeCache[count] is True:
                i['debrid_provider'] = 'premiumize'
                cache_list.append(i)
            count += 1

        self.premiumizeCached = cache_list
