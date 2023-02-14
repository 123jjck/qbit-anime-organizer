from qbittorrentapi import Client
import os, re, requests, sys, json

# determine if application is a script file or frozen exe
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
elif __file__:
    application_path = os.path.dirname(__file__)

config_path = os.path.join(application_path, 'config.json')

cfg_file = open(config_path, "r")
config = json.load(cfg_file)

# Config 
allowed_states = config['default']['qbit']['allowed_states']
allowed_categories = config['default']['qbit']['allowed_categories']
host = config['default']['qbit']['host']
username = config['default']['qbit']['username']
password = config['default']['qbit']['password']

client = Client(host=host, username=username, password=password)
torrent_hash = sys.argv[1]

torrent_info = client.torrents_info(torrent_hashes=torrent_hash)
torrent = torrent_info[0]

config_profile = 'default'
if(torrent.category in config['per-category-settings']):
    config_profile = torrent.category
    config = config['per-category-settings']

# Series moving settings
moving_enabled = config[config_profile]['series']['moving']['enabled']
default_season = config[config_profile]['series']['moving']['default_season'] # Default season number when is not specified manually
allow_manual_naming = config[config_profile]['series']['moving']['allow_manual_naming'] # This will prefer manual naming instead of AniLibria (still will try to get season number even if disabled)
move_to = config[config_profile]['series']['moving']['destination']
season_folder_name = config[config_profile]['series']['moving']['seasons_folder_name']

# AniLibria API config
api_host = config[config_profile]['api']['host']
fetch_from_AniLibria = config[config_profile]['api']['enable_fetching']
enable_hash_check = config[config_profile]['api']['enable_hash_check']


is_anilibria_torrent = False

def sanitize_filename(string):
    return "".join( x for x in string if (x.isalnum() or x in ".,_- ")).strip()

if torrent.state in allowed_states and torrent.progress == 1 and torrent.category in allowed_categories:
    torrent_download_path = torrent.save_path
    # ONLY FOR DEBUG
    #torrent_download_path = torrent_download_path.replace('/video/', '/home/hdd/Video/')
    torrent_folder_path = torrent.content_path

    if "AniLibria.TV" in torrent_folder_path: is_anilibria_torrent = True

    for file in client.torrents_files(torrent_hash=torrent_hash):
        file_path = os.path.join(torrent_download_path, file.name)

        if file.priority == 0: # Cleanup files which are not downloaded 
            if os.path.exists(file_path):
                print('[INFO] Clean unwanted file: %s' % file.name)
                os.remove(file_path)

        if file.progress == 1: # Progress files
            file_name = os.path.basename(file_path)
            if "_[AniLibria_TV]_" in file_name:

                new_file_name = re.sub(r"(.*)_\[(?<![\d.])(\d{1,2}|\d{0,2}\.\d{1,2})?(?![\d.])\]_\[AniLibria_TV]_", r"\g<1> \g<2> ", file_name)
                new_file_path = os.path.join(os.path.dirname(file.name), new_file_name)

                client.torrents_rename_file(torrent_hash=torrent_hash, old_path=file.name, new_path=new_file_path)

    if moving_enabled:
        title_name = os.path.basename(torrent_folder_path)
        season = default_season

        if is_anilibria_torrent and not allow_manual_naming: 
            title_quality = title_name.split(' - AniLibria.TV [')[1].split(']')[0]
            title_name = title_name.split(' -')[0]

            print(title_name)
            print(title_quality)

            if fetch_from_AniLibria: # Try to automatically fetch title from AniLibria
                search_request = requests.get('%s/v2/searchTitles' % api_host, params={'search': title_name})
                selected_title = None

                for title in search_request.json(): # Try to find right title
                    if title['type']['code'] == 0: 
                        print('[ERROR] This script don\'t support movies!')
                        continue

                    for parsedTorrent in title['torrents']['list']:
                        if parsedTorrent['quality']['string'] == title_quality:
                            if enable_hash_check and parsedTorrent['hash'] != torrent_hash: continue
                            selected_title = title
                            title_name = sanitize_filename(selected_title['names']['ru'])
                            break
                    if selected_title is not None: break 

        season_regex = re.compile(r'\[S\d{1,2}\]')
        print(torrent.name)
        if re.search(season_regex, torrent.name):
            season = int(re.search(season_regex, torrent.name).group(0).replace('[S', '').replace(']', ''))
            if allow_manual_naming: title_name = sanitize_filename(re.sub(season_regex, '', torrent.name))
            print(season, title_name)
        else:
            print('[WARN] We can\'t find season from torrent title! Using default season (%s) instead' % default_season)
        
        client.torrents_rename_folder(torrent_hash=torrent_hash, old_path=os.path.basename(torrent_folder_path), new_path=season_folder_name.replace('[n]', str(season)))

        client.torrents_set_location(torrent_hashes=torrent_hash, location=os.path.join(move_to, title_name))