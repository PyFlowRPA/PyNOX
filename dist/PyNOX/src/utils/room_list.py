"""
utils/room_list.py — hera.pet 공개 룸리스트 API
"""
import os
import re
import urllib.request
import json


_API_URL = "https://hera.pet/games.json"


def _map_words(text: str) -> "list[str]":
    """공백·언더스코어·하이픈을 구분자로 단어 목록 반환 (대문자)."""
    return re.sub(r"[\s_\-]+", " ", text).upper().split()


def fetch_rooms(map_keyword: str = "NOX") -> "list[dict]":
    """
    hera.pet/games.json 에서 status='open' 방만 가져온 뒤
    map 파일명에 map_keyword 의 모든 단어가 포함된 방만 반환.
    (공백·언더스코어·하이픈을 동일 구분자로 취급)

    반환 dict 필드:
        id       (int)  — 방 번호
        name     (str)  — 방 제목
        host     (str)  — 방장 닉네임
        map      (str)  — 맵 파일 경로 (원본)
        players  (int)  — 현재 인원
    """
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "PyNOX/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return []

    kw_words = _map_words(map_keyword)   # ["NOX", "RPG"]

    results = []
    for room in data:
        if not isinstance(room, dict):
            continue
        if room.get("status") != "open":
            continue
        map_path = room.get("map", "")
        map_filename = os.path.basename(map_path.replace("\\", "/"))
        filename_norm = " ".join(_map_words(map_filename))  # "NOX RPG V2 W3X"
        if kw_words and not all(w in filename_norm for w in kw_words):
            continue
        results.append({
            "id":      room.get("id"),
            "name":    room.get("name", ""),
            "host":    room.get("host", ""),
            "map":     map_path,
            "players": room.get("players", 0),
        })
    return results
