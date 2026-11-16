package org.saavndl;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.os.Build;
import android.os.SystemClock;
import android.view.Choreographer;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.graphics.Insets;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.webkit.WebView;
import android.widget.FrameLayout;
import org.json.JSONObject;

/** One persistent compositor-animated splash, outside the main WebView content. */
public final class StartupSplash {
    private static FrameLayout overlay;
    private static WebView splash;
    private static volatile boolean active;
    private static volatile int starts, frames, longFrames, layoutChanges;
    private static volatile long started, readyAt = -1, finishedAt = -1, maxFrameGap;
    private static long previousFrame;

    public static void show(Activity activity) {
        // Called once by PythonActivity.onCreate, before Python unpacking starts.
        if (overlay != null || starts > 0) return;
        starts++;
        active = true;
        started = SystemClock.uptimeMillis();
        Window window = activity.getWindow();
        window.setBackgroundDrawable(new ColorDrawable(Color.rgb(16,17,20)));
        window.setStatusBarColor(Color.rgb(16,17,20));
        window.setNavigationBarColor(Color.rgb(16,17,20));
        if (Build.VERSION.SDK_INT >= 29) window.setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 30) window.setDecorFitsSystemWindows(false);
        View decor = window.getDecorView();
        decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        overlay = new FrameLayout(activity);
        overlay.setBackgroundColor(Color.rgb(16,17,20));
        overlay.setClickable(true);
        overlay.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        overlay.setContentDescription("Starting SaavnDl");
        splash = new WebView(activity);
        splash.setBackgroundColor(Color.rgb(16,17,20));
        // Only local HTML/CSS/images. No JavaScript, network, or app data access.
        splash.getSettings().setJavaScriptEnabled(false);
        splash.getSettings().setDomStorageEnabled(false);
        splash.getSettings().setAllowContentAccess(false);
        splash.setOverScrollMode(View.OVER_SCROLL_NEVER);
        overlay.addView(splash,new FrameLayout.LayoutParams(-1,-1));
        overlay.setOnApplyWindowInsetsListener((view,insets) -> {
            int left,top,right,bottom;
            if (Build.VERSION.SDK_INT>=30) {
                Insets safe=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                left=safe.left;top=safe.top;right=safe.right;bottom=safe.bottom;
            } else {
                left=insets.getSystemWindowInsetLeft();top=insets.getSystemWindowInsetTop();
                right=insets.getSystemWindowInsetRight();bottom=insets.getSystemWindowInsetBottom();
            }
            FrameLayout.LayoutParams params=(FrameLayout.LayoutParams)splash.getLayoutParams();
            if (params.leftMargin!=left || params.topMargin!=top || params.rightMargin!=right || params.bottomMargin!=bottom) {
                params.setMargins(left,top,right,bottom);splash.setLayoutParams(params);
            }
            return insets;
        });
        // Direct decor sibling: setContentView() during unpacking cannot replace it.
        ((ViewGroup)decor).addView(overlay,new FrameLayout.LayoutParams(-1,-1));
        overlay.requestApplyInsets();
        overlay.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob) -> {
            if (or>ol && ob>ot && (l!=ol || t!=ot || r!=or || b!=ob)) layoutChanges++;
        });
        splash.loadUrl("file:///android_asset/_splash.html");
        Choreographer.getInstance().postFrameCallback(new Choreographer.FrameCallback() {
            @Override public void doFrame(long now) {
                if (!active) return;
                if (previousFrame != 0) {
                    long gap=(now-previousFrame)/1000000;
                    maxFrameGap=Math.max(maxFrameGap,gap);
                    if (gap>50) longFrames++;
                }
                previousFrame=now;frames++;
                Choreographer.getInstance().postFrameCallback(this);
            }
        });
    }

    public static void ready(Activity activity) {
        activity.runOnUiThread(() -> {
            if (!active || readyAt>=0 || overlay==null) return;
            readyAt=SystemClock.uptimeMillis()-started;
            // A fast warm launch still gets one complete, short intro.
            long delay=Math.max(0,1450-readyAt);
            overlay.postDelayed(() -> {
                if (overlay==null) return;
                overlay.animate().alpha(0f).setDuration(320)
                        .setInterpolator(new AccelerateDecelerateInterpolator())
                        .withEndAction(() -> {
                            FrameLayout old=overlay;
                            if (old!=null && old.getParent() instanceof ViewGroup)
                                ((ViewGroup)old.getParent()).removeView(old);
                            if (splash!=null) { splash.stopLoading(); splash.destroy(); }
                            overlay=null;splash=null;
                            finishedAt=SystemClock.uptimeMillis()-started;active=false;
                        }).start();
            },delay);
        });
    }

    public static String stats() {
        try {
            JSONObject data=new JSONObject();
            data.put("starts",starts);data.put("active",active);
            data.put("readyMs",readyAt);data.put("finishedMs",finishedAt);
            data.put("frames",frames);data.put("maxFrameGapMs",maxFrameGap);
            data.put("longFrames",longFrames);data.put("layoutChanges",layoutChanges);
            return data.toString();
        } catch(Exception ignored) { return "{}"; }
    }
}
