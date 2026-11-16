"""Install the native splash before Python unpacks, and use a dark launch theme."""
from pathlib import Path
import shutil


def before_apk_build(toolchain):
    root=Path(toolchain._dist.dist_dir)
    path=root/'src/main/java/org/kivy/android/PythonActivity.java'
    source=path.read_text()
    original='this.showLoadingScreen();'
    replacement='org.saavndl.StartupSplash.show(this);'
    if replacement not in source:
        if source.count(original)!=1:
            raise RuntimeError('PythonActivity startup changed; review the splash hook.')
        path.write_text(source.replace(original,replacement,1))
    template=root/'templates/AndroidManifest.tmpl.xml'
    source=template.read_text()
    if '@style/SaavnLaunchTheme' not in source:
        if '@style/KivySupportCutout' not in source:
            raise RuntimeError('Bootstrap activity theme changed; review the splash hook.')
        template.write_text(source.replace('@style/KivySupportCutout','@style/SaavnLaunchTheme'))


def after_apk_build(toolchain):
    root=Path(toolchain._dist.dist_dir)
    source=Path(__file__).resolve().parent/'startup/res'
    shutil.copytree(source,root/'src/main/res',dirs_exist_ok=True)
    if '@style/SaavnLaunchTheme' not in (root/'src/main/AndroidManifest.xml').read_text():
        raise RuntimeError('The native splash launch theme was not applied.')
