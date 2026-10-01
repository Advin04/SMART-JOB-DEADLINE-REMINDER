"""
Tiny JSON store in the user's own Google Drive appDataFolder (scope
drive.appdata). No database: the file lives in the user's Drive, is invisible
in their Drive UI, is only reachable by this app, and is deleted when they
revoke access.

Files used: profile.json (written by the website), state.json (background job).
"""
import io
import json
import os
from typing import Dict, Optional

PROFILE_FILE = 'profile.json'
STATE_FILE = 'state.json'
MAX_BYTES = 256 * 1024          # appDataFolder is for small settings, not bulk data
LOCAL_STORE_DIR = os.path.join(os.path.dirname(__file__), '.vault_data')


class DriveStore:
    def __init__(self, service):
        self.svc = service

    def _local_path(self, name: str) -> str:
        os.makedirs(LOCAL_STORE_DIR, exist_ok=True)
        return os.path.join(LOCAL_STORE_DIR, name)

    def _find(self, name: str) -> Optional[str]:
        if not self.svc:
            return None
        try:
            safe = name.replace("\\", "\\\\").replace("'", "\\'")
            res = self.svc.files().list(spaces='appDataFolder', q=f"name = '{safe}'",
                                        fields='files(id,name,modifiedTime)', pageSize=10).execute()
            files = res.get('files', [])
            return files[0]['id'] if files else None
        except Exception as e:
            print(f"⚠️ DriveStore _find error: {e}")
            return None

    def load(self, name: str) -> Optional[Dict]:
        if self.svc:
            try:
                file_id = self._find(name)
                if file_id:
                    raw = self.svc.files().get_media(fileId=file_id).execute()
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode('utf-8')
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                print(f"⚠️ DriveStore load error: {e}")

        # Local fallback
        path = self._local_path(name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else None
            except Exception as le:
                print(f"⚠️ LocalStore load error: {le}")
        return None

    def save(self, name: str, data: Dict) -> None:
        if self.svc:
            try:
                payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                if len(payload) <= MAX_BYTES:
                    from googleapiclient.http import MediaIoBaseUpload
                    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype='application/json', resumable=False)
                    file_id = self._find(name)
                    if file_id:
                        self.svc.files().update(fileId=file_id, media_body=media).execute()
                    else:
                        self.svc.files().create(body={'name': name, 'parents': ['appDataFolder']},
                                                media_body=media, fields='id').execute()
            except Exception as e:
                print(f"⚠️ DriveStore save error: {e}")

        # Always save locally as fallback / mirror
        try:
            path = self._local_path(name)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        except Exception as le:
            print(f"⚠️ LocalStore save error: {le}")

    def delete(self, name: str) -> None:
        if self.svc:
            try:
                file_id = self._find(name)
                if file_id:
                    self.svc.files().delete(fileId=file_id).execute()
            except Exception as e:
                print(f"⚠️ DriveStore delete error: {e}")

        path = self._local_path(name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as le:
                print(f"⚠️ LocalStore delete error: {le}")

    def list_names(self, prefix: str = '') -> list:
        names = set()
        if self.svc:
            try:
                token = None
                while True:
                    res = self.svc.files().list(spaces='appDataFolder', fields='nextPageToken,files(name)', pageSize=100, pageToken=token).execute()
                    names.update(f['name'] for f in res.get('files', []) if f['name'].startswith(prefix))
                    token = res.get('nextPageToken')
                    if not token:
                        break
            except Exception as e:
                print(f"⚠️ DriveStore list_names error: {e}")

        # Local fallback names
        if os.path.exists(LOCAL_STORE_DIR):
            try:
                for fname in os.listdir(LOCAL_STORE_DIR):
                    if fname.startswith(prefix):
                        names.add(fname)
            except Exception as le:
                print(f"⚠️ LocalStore list_names error: {le}")
        return list(names)

