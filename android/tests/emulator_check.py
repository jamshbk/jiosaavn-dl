"""Launch the real APK and check Android MediaStore writes from a native worker."""
import subprocess
import time
from pathlib import Path
import requests


def adb(*args, check=True):
    return subprocess.run(['adb',*args],check=check,text=True,capture_output=True).stdout


apk=Path('android/Saavn-Pocket-v0.2.1-debug.apk')
adb('install','-r',str(apk))
adb('logcat','-c')
adb('shell','am','start','-W','-n','org.example.saavnpocket/org.kivy.android.PythonActivity',
    '--ez','saavn_native_test','true')
deadline=time.monotonic()+120
success=False
while time.monotonic()<deadline:
    log=adb('logcat','-d')
    if 'SAAVN_NATIVE_CHECK_FAILED' in log:
        break
    if 'SAAVN_NATIVE_CHECK_OK' in log:
        success=True
        break
    time.sleep(2)
Path('android/native-check.log').write_text(log,encoding='utf-8')
if not success:
    lines=[line for line in log.splitlines() if any(s in line for s in ('python','Python','FATAL','SAAVN_'))]
    raise SystemExit('Android native storage check failed:\n'+'\n'.join(lines[-100:]))
adb('forward','tcp:5051','tcp:5000')
for attempt in range(30):
    try:
        response=requests.get('http://127.0.0.1:5051/',timeout=3)
        response.raise_for_status()
        assert 'Saavn Pocket' in response.text
        assert 'archive-form' in response.text
        break
    except Exception:
        if attempt==29:
            raise
        time.sleep(1)
print('PASS: Actual Android APK launched; worker-thread MediaStore export, byte-for-byte readback and deletion succeeded; app UI server responds.')
