"""Launch the real APK and check Android MediaStore writes from a native worker."""
import subprocess
import time
from pathlib import Path
import requests
import re
import json
import xml.etree.ElementTree as ET


def adb(*args, check=True):
    return subprocess.run(['adb',*args],check=check,text=True,capture_output=True).stdout


apk=Path('android/JS-DL-v3.0.apk')
adb('install','-r',str(apk))
# Keep software-GPU capture representative and avoid 1080p encoder overload.
adb('shell','wm','size','540x960')
adb('shell','wm','density','240')
# Cold-boot system overlays can still be applying after sys.boot_completed.
time.sleep(20)
adb('logcat','-c')
previews=Path('android/native-previews');previews.mkdir(exist_ok=True)
# Record the actual cold startup with Android's animator scale enabled.
for name in ('window_animation_scale','transition_animation_scale','animator_duration_scale'):
    adb('shell','settings','put','global',name,'1.0')
recording=subprocess.Popen(['adb','shell','screenrecord','--bit-rate','2000000','--time-limit','180','/sdcard/saavndl-startup.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(.5)
adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity',
    '--ez','saavn_native_test','true')
deadline=time.monotonic()+360
success=False
restarted=False
while time.monotonic()<deadline:
    log=adb('logcat','-d')
    if 'SAAVN_NATIVE_CHECK_FAILED' in log:
        break
    if 'SAAVN_NATIVE_CHECK_OK' in log:
        success=True
        break
    if not restarted and not adb('shell','pidof','org.example.saavnpocket',check=False).strip():
        time.sleep(3)
        adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity','--ez','saavn_native_test','true')
        restarted=True
    time.sleep(2)
Path('android/native-check-result.txt').write_text('PENDING additional checks' if success else 'FAIL',encoding='utf-8')
if not success:
    lines=[line for line in log.splitlines() if any(s in line for s in ('python','Python','FATAL','SAAVN_','AndroidRuntime','libc','DEBUG','am_crash'))]
    raise SystemExit('Android native storage check failed:\n'+'\n'.join(lines[-100:]))
adb('forward','tcp:5051','tcp:5000')
for attempt in range(30):
    try:
        response=requests.get('http://127.0.0.1:5051/',timeout=3)
        response.raise_for_status()
        assert 'JS-DL' in response.text
        assert 'archive-form' in response.text
        break
    except Exception:
        if attempt==29:
            raise
        time.sleep(1)
token=re.search(r'name="app-token" content="([^"]+)"',response.text).group(1)
headers={'Host':'127.0.0.1:5000','X-App-Token':token}
def api(route,body=None):
    request=requests.get if body is None else requests.post
    result=request('http://127.0.0.1:5051/api/'+route,headers=headers,timeout=35,**({} if body is None else {'json':body}))
    result.raise_for_status()
    return result.json()

# Ready comes from the real main-page render, not from the test.
for attempt in range(60):
    startup=api('startup')
    if startup.get('starts')==1 and not startup.get('active'):
        break
    time.sleep(.5)
else:raise AssertionError('Continuous splash did not hand off to the home page: '+json.dumps(startup))
assert startup['readyMs']>=0 and startup['finishedMs']>=1450,startup
assert startup['layoutChanges']==0 and startup['coreLayoutChanges']==0,startup
assert startup['frames']>10,startup
assert startup['measureConfigurations']<=3 and startup['measurePasses']<100,startup
(previews/'startup-timing.json').write_text(json.dumps(startup),encoding='utf-8')
time.sleep(1)
adb('shell','pkill','-2','screenrecord',check=False)
try:recording.wait(timeout=15)
except subprocess.TimeoutExpired:recording.kill();recording.wait()
adb('pull','/sdcard/saavndl-startup.mp4',str(previews/'startup.mp4'))
assert (previews/'startup.mp4').stat().st_size>10000

def check_insets(label,landscape=False):
    deadline=time.monotonic()+30
    last={}
    while time.monotonic()<deadline:
        last=api('device')
        if last.get('width',0)>0 and bool(last['width']>last['height'])==landscape and last.get('contentRight',0)>0:
            if (last['paddingLeft']>=last['left'] and last['paddingTop']>=last['top'] and
                last['paddingRight']>=last['right'] and last['paddingBottom']>=last['bottom'] and
                last['contentLeft']>=last['left']-2 and last['contentTop']>=last['top']-2 and
                last['contentRight']<=last['width']-last['right']+2 and
                last['contentBottom']<=last['height']-last['bottom']+2):
                time.sleep(1)
                screenshot=subprocess.run(['adb','exec-out','screencap','-p'],check=True,capture_output=True).stdout
                (previews/(label+'.png')).write_bytes(screenshot)
                return last
        time.sleep(1)
    raise AssertionError('Native content overlaps system bars or did not rotate: '+json.dumps(last))

time.sleep(2)
check_insets('portrait')
adb('shell','settings','put','system','accelerometer_rotation','1')
adb('emu','sensor','set','acceleration','9.8:0:0')
check_insets('landscape',True)
adb('emu','sensor','set','acceleration','0:9.8:0')
check_insets('portrait-restored')
overlays=adb('shell','cmd','overlay','list',check=False)
if 'com.android.internal.systemui.navbar.gestural' in overlays:
    adb('shell','cmd','overlay','enable-exclusive','--category','com.android.internal.systemui.navbar.gestural',check=False)
    # Applying a system resource overlay may recreate the process. Reopen the
    # app, as a user does after changing Android navigation settings.
    time.sleep(5)
    adb('shell','am','force-stop','org.example.saavnpocket')
    adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity','--ez','saavn_native_test','true')
    for attempt in range(45):
        try:
            response=requests.get('http://127.0.0.1:5051/',timeout=2)
            token=re.search(r'name="app-token" content="([^"]+)"',response.text).group(1)
            headers['X-App-Token']=token
            api('device')
            break
        except Exception:
            if attempt==44:raise
            time.sleep(1)
    check_insets('gesture-navigation')

# Select a real folder through Android's own picker, then verify its persisted grant.
adb('shell','mkdir','-p','/sdcard/Documents/SaavnDl-CI')
api('folder/pick',{})
entered=False
deadline=time.monotonic()+75
while time.monotonic()<deadline:
    destination=api('destination')
    if not destination['pending']:
        assert destination.get('uri') and 'SaavnDl-CI' in destination.get('path',''),destination
        break
    adb('shell','uiautomator','dump','/sdcard/saavndl-picker.xml',check=False)
    text=adb('shell','cat','/sdcard/saavndl-picker.xml',check=False)
    try: nodes=list(ET.fromstring(text).iter('node'))
    except ET.ParseError:
        time.sleep(1);continue
    candidates=[]
    for node in nodes:
        label=(node.get('text') or node.get('content-desc') or '').strip()
        if not entered and label=='SaavnDl-CI':candidates=[node];entered=True;break
        if entered and (label.lower() in ('use this folder','allow','select') or (label.lower().startswith('allow access to') and node.get('clickable')=='true') or node.get('resource-id','').endswith('/action_menu_select')):candidates.append(node)
    if not candidates and not entered:
        # Older DocumentsUI versions may ignore EXTRA_INITIAL_URI.
        for wanted in ('Documents','Internal storage','Pixel 2','Show roots','Show navigation drawer'):
            matches=[node for node in nodes if (node.get('text') or node.get('content-desc') or '').strip()==wanted]
            if matches:
                candidates=matches[:1]
                break
    if candidates:
        bounds=list(map(int,re.findall(r'\d+',candidates[0].get('bounds',''))))
        if len(bounds)==4:adb('shell','input','tap',str((bounds[0]+bounds[2])//2),str((bounds[1]+bounds[3])//2))
    time.sleep(1)
else:
    (previews/'folder-picker-failure.png').write_bytes(subprocess.run(['adb','exec-out','screencap','-p'],check=True,capture_output=True).stdout)
    labels=[(node.get('text') or node.get('content-desc') or '',node.get('resource-id','')) for node in nodes]
    raise AssertionError('Android folder picker did not complete: '+json.dumps(labels))
assert api('native-check-folder',{})['ok']
saved_uri=api('destination')['uri']
time.sleep(1)
adb('shell','am','force-stop','org.example.saavnpocket')
adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity','--ez','saavn_native_test','true')
for attempt in range(45):
    try:
        response=requests.get('http://127.0.0.1:5051/',timeout=2)
        token=re.search(r'name="app-token" content="([^"]+)"',response.text).group(1)
        headers['X-App-Token']=token
        assert api('destination')['uri']==saved_uri
        break
    except Exception:
        if attempt==44:raise
        time.sleep(1)
assert api('native-check-folder',{})['ok']
api('folder/default',{})
assert not api('destination')['uri']
# Repeat an ordinary launch after unpacking: this is the everyday user startup.
adb('shell','am','force-stop','org.example.saavnpocket')
recording=subprocess.Popen(['adb','shell','screenrecord','--bit-rate','2000000','--time-limit','180','/sdcard/saavndl-startup-warm.mp4'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(.5)
adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity')
for attempt in range(60):
    try:
        response=requests.get('http://127.0.0.1:5051/',timeout=2)
        headers['X-App-Token']=re.search(r'name="app-token" content="([^"]+)"',response.text).group(1)
        warm=api('startup')
        if warm.get('starts')==1 and not warm.get('active'):break
    except (requests.RequestException,AttributeError):pass
    time.sleep(.5)
else:raise AssertionError('Warm startup did not complete.')
assert warm['layoutChanges']==0 and warm['coreLayoutChanges']==0 and warm['animationEngine']=='native-vector',warm
assert warm['readyMs']>=0 and warm['finishedMs']>=1450,warm
assert warm['measureConfigurations']<=3 and warm['measurePasses']<100,warm
(previews/'startup-warm-timing.json').write_text(json.dumps(warm),encoding='utf-8')
# Confirm the visible home UI before stopping the video, not just a timer.
for attempt in range(10):
    adb('shell','uiautomator','dump','/sdcard/saavndl-home.xml',check=False)
    hierarchy=adb('shell','cat','/sdcard/saavndl-home.xml',check=False)
    if 'Archive' in hierarchy and 'Starting JS-DL' not in hierarchy:break
    time.sleep(.5)
else:raise AssertionError('Home screen was not visibly available after splash handoff.')
time.sleep(2)
adb('shell','pkill','-2','screenrecord',check=False)
try:recording.wait(timeout=15)
except subprocess.TimeoutExpired:recording.kill();recording.wait()
adb('pull','/sdcard/saavndl-startup-warm.mp4',str(previews/'startup-warm.mp4'))
assert (previews/'startup-warm.mp4').stat().st_size>10000
print('PASS: cold and warm native splash, stable layout, home-ready handoff and animation-enabled videos.')


Path('android/native-check-result.txt').write_text('PASS: MediaStore worker export, native system-bar insets, rotation, custom folder write/readback and persisted permission after restart.',encoding='utf-8')
print('PASS: Actual Android APK storage, system-bar insets, rotation, custom folder picker, readback and persistent grants after restart.')
