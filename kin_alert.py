# 네이버 지식인 "분양, 청약" 분야(dirId 40203) 새 질문을 카카오톡 "나와의 채팅"으로 알려 주는 프로그램.
# GitHub Actions가 10분마다 실행한다(.github/workflows/alert.yml).
#
# 필요한 금고(Secrets): KAKAO_REST_KEY (카카오 앱의 REST API 키), KAKAO_CLIENT_SECRET(쓰는 앱만)
# 카톡 토큰(refresh token)은 REST 키로 암호화해 state/token.enc에 저장한다.
# 카카오는 남은 기간이 한 달 아래일 때 새 토큰을 주므로, 받을 때마다 저장해 두면 다시 로그인할 필요가 없다.
#
# 사용:
#   python kin_alert.py connect <인가코드>   카톡 처음 연결(kakao-connect.yml)
#   python kin_alert.py                      새 질문 확인·알림(alert.yml)
import base64, hashlib, html, json, os, re, sys, urllib.parse, urllib.request
from cryptography.fernet import Fernet

DIR_ID = '40203'
LIST_URL = f'https://kin.naver.com/qna/list.naver?dirId={DIR_ID}'
REDIRECT_URI = 'https://yongbro95.com'
STATE = 'state/seen.json'
TOKEN = 'state/token.enc'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0 Safari/537.36')

REST_KEY = os.environ['KAKAO_REST_KEY']
CLIENT_SECRET = os.environ.get('KAKAO_CLIENT_SECRET', '')
fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(REST_KEY.encode()).digest()))


def post(url, data, headers=None):
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f'{url} 실패 {e.code}: {e.read().decode()[:300]}')


def kakao_token(grant):
    data = {'client_id': REST_KEY, **grant}
    if CLIENT_SECRET:
        data['client_secret'] = CLIENT_SECRET
    return post('https://kauth.kakao.com/oauth/token', data)


def save_refresh(token):
    with open(TOKEN, 'wb') as f:
        f.write(fernet.encrypt(token.encode()))


def send(access, text, link):
    tpl = {'object_type': 'text', 'text': text[:200],
           'link': {'web_url': link, 'mobile_web_url': link}, 'button_title': '질문 보기'}
    post('https://kapi.kakao.com/v2/api/talk/memo/default/send',
         {'template_object': json.dumps(tpl, ensure_ascii=False)},
         {'Authorization': f'Bearer {access}'})


def fetch_questions():
    req = urllib.request.Request(LIST_URL, headers={'User-Agent': UA, 'Accept-Language': 'ko-KR'})
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read().decode('utf-8', 'replace')
    found = {}
    for m in re.finditer(r'<a[^>]+href="([^"]*detail\.naver\?[^"]*docId=(\d+)[^"]*)"[^>]*>(.*?)</a>', page, re.S):
        title = html.unescape(re.sub(r'<.*?>', '', m.group(3))).strip()
        if title and m.group(2) not in found:
            found[m.group(2)] = title
    print(f'목록 화면 {len(page)}자, 질문 {len(found)}개')
    if not found:
        sys.exit('목록 화면에서 질문을 못 찾았어요(화면 구조가 바뀌었거나 막힘)')
    return found


def main():
    if len(sys.argv) == 3 and sys.argv[1] == 'connect':
        tok = kakao_token({'grant_type': 'authorization_code', 'redirect_uri': REDIRECT_URI, 'code': sys.argv[2]})
        save_refresh(tok['refresh_token'])
        send(tok['access_token'], '지식인 알림이 카톡에 연결됐어요.', 'https://kin.naver.com/qna/list.naver?dirId=' + DIR_ID)
        print('연결 완료')
        return

    questions = fetch_questions()
    if not os.path.exists(TOKEN):
        print('카톡 연결 전이라 알림은 건너뜀')
        return
    refresh = fernet.decrypt(open(TOKEN, 'rb').read()).decode()
    tok = kakao_token({'grant_type': 'refresh_token', 'refresh_token': refresh})
    if tok.get('refresh_token'):
        save_refresh(tok['refresh_token'])
        print('카톡 토큰 연장함')
    access = tok['access_token']

    seen = json.load(open(STATE)) if os.path.exists(STATE) else []
    new = [d for d in questions if d not in seen]
    if not seen:
        send(access, f'지식인 알림을 시작했어요. 지금 목록의 질문 {len(questions)}개는 건너뛰고 새 질문부터 알려 드릴게요.', LIST_URL)
    else:
        for d in sorted(new, key=int):
            link = f'https://kin.naver.com/qna/detail.naver?dirId={DIR_ID}&docId={d}'
            send(access, f'[지식인 새 질문]\n{questions[d]}', link)
    print(f'새 질문 {len(new)}개')
    json.dump((seen + sorted(new, key=int))[-500:], open(STATE, 'w'))


if __name__ == '__main__':
    main()
