package org.saavndl;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.Insets;
import android.graphics.drawable.AnimatedVectorDrawable;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.ColorDrawable;
import android.os.Build;
import android.os.SystemClock;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.util.TypedValue;
import android.view.Choreographer;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.InputStream;
import org.json.JSONObject;

/** One lightweight native overlay. The waveform runs on Android's RenderThread. */
public final class StartupSplash {
    private static FrameLayout overlay;
    private static AnimatedVectorDrawable wave;
    private static ObjectAnimator breathing;
    private static volatile boolean active;
    private static volatile int starts, frames, longFrames, layoutChanges;
    private static volatile long started, readyAt=-1, finishedAt=-1, maxFrameGap;
    private static long previousFrame;
    private static int dp(Activity a,float value) { return Math.round(value*a.getResources().getDisplayMetrics().density); }
    private static TextView text(Activity a,String value,int color,float size) {
        TextView label=new TextView(a);label.setText(value);label.setTextColor(color);
        label.setTextSize(TypedValue.COMPLEX_UNIT_DIP,size);label.setIncludeFontPadding(false);
        return label;
    }

    public static void show(Activity activity) {
        if (overlay!=null || starts>0) return;
        starts++;active=true;started=SystemClock.uptimeMillis();
        Window window=activity.getWindow();
        window.setBackgroundDrawable(new ColorDrawable(Color.rgb(16,17,20)));
        window.setStatusBarColor(Color.rgb(16,17,20));window.setNavigationBarColor(Color.rgb(16,17,20));
        if (Build.VERSION.SDK_INT>=29) window.setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT>=30) window.setDecorFitsSystemWindows(false);
        View decor=window.getDecorView();
        decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        overlay=new FrameLayout(activity);overlay.setClickable(true);overlay.setContentDescription("Starting SaavnDl");
        // Pre-render the static glow once, instead of shading an entire WebView every frame.
        Bitmap glow=Bitmap.createBitmap(256,512,Bitmap.Config.ARGB_8888);
        Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setShader(new RadialGradient(128,215,320,new int[]{Color.rgb(7,42,53),Color.rgb(8,18,29),Color.rgb(13,15,22)},new float[]{0,.5f,1},Shader.TileMode.CLAMP));
        new Canvas(glow).drawRect(0,0,256,512,paint);
        BitmapDrawable background=new BitmapDrawable(activity.getResources(),glow);background.setGravity(Gravity.FILL);
        overlay.setBackground(background);
        FrameLayout safe=new FrameLayout(activity);overlay.addView(safe,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout core=new LinearLayout(activity);core.setGravity(Gravity.CENTER);core.setAlpha(0);
        safe.addView(core,new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER));
        ImageView logo=new ImageView(activity);logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        try(InputStream input=activity.getAssets().open("startup-logo.png")) { logo.setImageBitmap(BitmapFactory.decodeStream(input)); }
        catch(Exception error) { logo.setImageResource(activity.getApplicationInfo().icon); }
        core.addView(logo,new LinearLayout.LayoutParams(dp(activity,180),dp(activity,180)));
        LinearLayout labels=new LinearLayout(activity);labels.setOrientation(LinearLayout.VERTICAL);labels.setGravity(Gravity.CENTER_HORIZONTAL);
        core.addView(labels,new LinearLayout.LayoutParams(-2,-2));
        TextView title=text(activity,"SaavnDl",Color.rgb(238,237,242),38);title.setTypeface(Typeface.DEFAULT,Typeface.BOLD);title.setLetterSpacing(-.045f);
        SpannableString name=new SpannableString("SaavnDl");name.setSpan(new ForegroundColorSpan(Color.rgb(33,202,213)),5,7,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);title.setText(name);
        labels.addView(title,new LinearLayout.LayoutParams(-2,-2));
        TextView tagline=text(activity,"SEARCH. PLAY. SAVE.",Color.rgb(140,174,189),12);tagline.setLetterSpacing(.25f);
        LinearLayout.LayoutParams tagParams=new LinearLayout.LayoutParams(-2,-2);tagParams.topMargin=dp(activity,8);labels.addView(tagline,tagParams);
        ImageView bars=new ImageView(activity);
        int resource=activity.getResources().getIdentifier("startup_wave_animated","drawable",activity.getPackageName());
        wave=(AnimatedVectorDrawable)activity.getDrawable(resource);bars.setImageDrawable(wave);
        LinearLayout.LayoutParams waveParams=new LinearLayout.LayoutParams(dp(activity,40),dp(activity,28));waveParams.topMargin=dp(activity,26);labels.addView(bars,waveParams);
        TextView version=text(activity,"Version 1.0",Color.rgb(100,117,131),11);version.setLetterSpacing(.09f);
        FrameLayout.LayoutParams versionParams=new FrameLayout.LayoutParams(-2,-2,Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);versionParams.bottomMargin=dp(activity,25);safe.addView(version,versionParams);
        safe.addOnLayoutChangeListener((view,l,t,r,b,ol,ot,or,ob) -> {
            boolean landscape=r-l>b-t && b-t<dp(activity,480);
            int size=landscape?dp(activity,130):Math.max(dp(activity,140),Math.min(dp(activity,230),Math.round((r-l)*.43f)));
            core.setOrientation(landscape?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL);
            LinearLayout.LayoutParams imageParams=(LinearLayout.LayoutParams)logo.getLayoutParams();
            if (imageParams.width!=size) { imageParams.width=size;imageParams.height=size;logo.setLayoutParams(imageParams); }
            LinearLayout.LayoutParams labelParams=(LinearLayout.LayoutParams)labels.getLayoutParams();
            int left=landscape?dp(activity,24):0,top=landscape?0:dp(activity,20);
            if(labelParams.leftMargin!=left || labelParams.topMargin!=top) {labelParams.leftMargin=left;labelParams.topMargin=top;labels.setLayoutParams(labelParams);}
            labels.setGravity(landscape?Gravity.LEFT:Gravity.CENTER_HORIZONTAL);
            title.setTextSize(TypedValue.COMPLEX_UNIT_DIP,landscape?32:38);
            tagline.setTextSize(TypedValue.COMPLEX_UNIT_DIP,landscape?10:12);
        });
        overlay.setOnApplyWindowInsetsListener((view,insets) -> {
            int left,top,right,bottom;
            if(Build.VERSION.SDK_INT>=30) {Insets margins=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());left=margins.left;top=margins.top;right=margins.right;bottom=margins.bottom;}
            else {left=insets.getSystemWindowInsetLeft();top=insets.getSystemWindowInsetTop();right=insets.getSystemWindowInsetRight();bottom=insets.getSystemWindowInsetBottom();}
            FrameLayout.LayoutParams params=(FrameLayout.LayoutParams)safe.getLayoutParams();
            if(params.leftMargin!=left || params.topMargin!=top || params.rightMargin!=right || params.bottomMargin!=bottom) {params.setMargins(left,top,right,bottom);safe.setLayoutParams(params);}
            return insets;
        });
        ((ViewGroup)decor).addView(overlay,new FrameLayout.LayoutParams(-1,-1));overlay.requestApplyInsets();
        overlay.addOnLayoutChangeListener((view,l,t,r,b,ol,ot,or,ob) -> {if(or>ol && ob>ot && (l!=ol || t!=ot || r!=or || b!=ob))layoutChanges++;});
        core.postOnAnimation(() -> core.postOnAnimation(() -> {
            core.animate().alpha(1).setDuration(600).start();wave.start();
            breathing=ObjectAnimator.ofFloat(logo,"alpha",.92f,1f,.92f);breathing.setDuration(2300);breathing.setRepeatCount(ValueAnimator.INFINITE);breathing.start();
        }));
        Choreographer.getInstance().postFrameCallback(new Choreographer.FrameCallback() {
            @Override public void doFrame(long now) {
                if(!active)return;
                if(previousFrame!=0) {long gap=(now-previousFrame)/1000000;maxFrameGap=Math.max(maxFrameGap,gap);if(gap>50)longFrames++;}
                previousFrame=now;frames++;Choreographer.getInstance().postFrameCallback(this);
            }
        });
    }

    public static void ready(Activity activity) {
        activity.runOnUiThread(() -> {
            if(!active || readyAt>=0 || overlay==null)return;
            readyAt=SystemClock.uptimeMillis()-started;
            overlay.postDelayed(() -> {
                if(overlay==null)return;
                overlay.animate().alpha(0).setDuration(320).setInterpolator(new AccelerateDecelerateInterpolator()).withEndAction(() -> {
                    if(wave!=null)wave.stop();if(breathing!=null)breathing.cancel();
                    FrameLayout old=overlay;if(old!=null && old.getParent() instanceof ViewGroup)((ViewGroup)old.getParent()).removeView(old);
                    overlay=null;wave=null;breathing=null;finishedAt=SystemClock.uptimeMillis()-started;active=false;
                }).start();
            },Math.max(0,1450-readyAt));
        });
    }

    public static String stats() {
        try {JSONObject data=new JSONObject();data.put("starts",starts);data.put("active",active);data.put("readyMs",readyAt);data.put("finishedMs",finishedAt);data.put("frames",frames);data.put("maxFrameGapMs",maxFrameGap);data.put("longFrames",longFrames);data.put("layoutChanges",layoutChanges);data.put("animationEngine","native-vector");return data.toString();}
        catch(Exception ignored){return "{}";}
    }
}
