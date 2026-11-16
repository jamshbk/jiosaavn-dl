"""Replace the bootstrap ImageView with one persistent native splash overlay."""
from pathlib import Path


def before_apk_build(toolchain):
    path = Path(toolchain._dist.dist_dir) / 'src/main/java/org/kivy/android/PythonActivity.java'
    source = path.read_text()
    original = 'this.showLoadingScreen();'
    replacement = 'org.saavndl.StartupSplash.show(this);'
    if replacement not in source:
        if source.count(original) != 1:
            raise RuntimeError('PythonActivity startup changed; review the splash hook before building.')
        path.write_text(source.replace(original, replacement, 1))
