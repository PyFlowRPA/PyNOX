"""
src/constants.py — 프로젝트 전역 상수
"""


class IMG:
    """이미지 매칭 파일명 상수 (image_search/ 폴더 기준)"""

    # ── 로그인 / 로비 ─────────────────────────────────────────────────────
    MAIN_SCREEN          = "1.메인화면.png"
    LOGIN_ENTER          = "2.로그인화면입장감지.png"
    LOGIN_SCREEN         = "3.로그인화면.png"
    LOBBY                = "4.로비체크.png"
    CUSTOM_CHANNEL       = "5.커스텀채널입장.png"
    LOGIN_WRONG_PW       = "6.로그인비밀번호틀렸을때.png"
    ROOM_LIST            = "7.방목록입장.png"
    ROOM_ENTER           = "8.방입장체크(동맹).png"
    ROOM_CREATE          = "9.방만들기(방장만).png"
    ROOM_PRIVATE         = "10.비공개게임.png"

    # ── 로딩 / 인게임 진입 ────────────────────────────────────────────────
    LOADING_DONE         = "11.로딩완료.png"
    LOADING_TIMEOUT      = "12.인원수타임아웃강제시작.png"
    LOADING_CURSOR       = "13.로딩완료후커서이동.png"
    INGAME_CHECK         = "14.인게임체크.png"

    # ── 캐릭터 선택 ───────────────────────────────────────────────────────
    CHAR_SWORD           = "15.검성.png"
    CHAR_TEMPLAR         = "16.템플러.png"
    CHAR_HUNTER          = "17.사냥꾼.png"
    CHAR_MAGE            = "18.마도사.png"
    CHAR_LANCER          = "19.창술사.png"
    CHAR_SWORDSMAN       = "20.검객.png"
    CHAR_SELECT          = "21.캐릭터선택체크.png"
    UNIT_GROUP           = "22.부대지정체크.png"
    ATTENDANCE           = "23.출석체크.png"

    # ── 자동사냥 설정 ─────────────────────────────────────────────────────
    HUNT_STAY            = "24.제자리사냥.png"
    HUNT_RADIUS          = "25.사냥반경.png"
    HUNT_DIALOG          = "26.자동사냥다이얼로그.png"
    HUNT_STAY_OFF        = "27.제자리OFF.png"
    HUNT_DIALOG_CONFIRM  = "28.자동사냥다이얼로그컨펌버튼.png"

    # ── 전투 상태 ─────────────────────────────────────────────────────────
    MOVE                 = "29.이동.png"
    MOVE_X               = "30.이동(X).png"
    STOP                 = "31.정지.png"
    STOP_X               = "32.정지(X).png"
    ATTACK               = "33.공격.png"
    ATTACK_X             = "34.공격(x).png"

    # ── 포탈 / 홀드 검증 ──────────────────────────────────────────────────
    PORTAL_CHECK         = "35.포탈검증.png"
    HOLD_CHECK           = "36.홀드검증.png"
    HUNT_ON_CHECK        = "37.자동사냥ON검증.png"

    # ── 사망 / 미션 종료 ──────────────────────────────────────────────────
    DEATH_1              = "38.사망로직.png"
    DEATH_2              = "39.사망로직.png"
    DEATH_3              = "40.사망로직.png"
    MISSION_END          = "41.미션종료.png"
    PLAYER_LEFT          = "42.플레이어나감인식.png"
