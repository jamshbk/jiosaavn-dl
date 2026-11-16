package org.saavndl;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.provider.DocumentsContract;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.webkit.WebView;
import org.json.JSONObject;
import org.kivy.android.PythonActivity;
import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.io.FileOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Insets and user-granted document-tree access. Loaded on Python's entry thread. */
public final class NativeUi implements PythonActivity.ActivityResultListener {
    private static final int FOLDER_REQUEST = 6814;
    private static PythonActivity activity;
    private static volatile boolean choosing = false;
    private static volatile String folderError = "";
    private static volatile String metrics = "{}";
    private static final int[] bars = new int[]{0,0,0,0};

    private static void recordMetrics(View content, View decor) {
        try {
            JSONObject data=new JSONObject();
            data.put("left",bars[0]); data.put("top",bars[1]); data.put("right",bars[2]); data.put("bottom",bars[3]);
            data.put("paddingLeft",content.getPaddingLeft()); data.put("paddingTop",content.getPaddingTop());
            data.put("paddingRight",content.getPaddingRight()); data.put("paddingBottom",content.getPaddingBottom());
            data.put("width",decor.getWidth()); data.put("height",decor.getHeight());
            if (content instanceof android.view.ViewGroup && ((android.view.ViewGroup)content).getChildCount()>0) {
                View child=((android.view.ViewGroup)content).getChildAt(0);
                int[] origin=new int[2]; child.getLocationOnScreen(origin);
                data.put("contentLeft",origin[0]); data.put("contentTop",origin[1]);
                data.put("contentRight",origin[0]+child.getWidth()); data.put("contentBottom",origin[1]+child.getHeight());
            }
            metrics=data.toString();
        } catch (Exception ignored) {}
    }

    public static synchronized void install(PythonActivity current) {
        if (activity == current) return;
        activity = current;
        activity.runOnUiThread(() -> {
            activity.registerActivityResultListener(new NativeUi());
            Window window = activity.getWindow();
            if ((activity.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0)
                WebView.setWebContentsDebuggingEnabled(true);
            window.setStatusBarColor(Color.rgb(16,15,20));
            window.setNavigationBarColor(Color.rgb(16,15,20));
            if (Build.VERSION.SDK_INT >= 29) window.setNavigationBarContrastEnforced(false);
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
            View decor = window.getDecorView();
            if (Build.VERSION.SDK_INT >= 30) window.setDecorFitsSystemWindows(false);
            decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
            View content = activity.findViewById(android.R.id.content);
            content.setBackgroundColor(Color.rgb(16,15,20));
            content.getViewTreeObserver().addOnGlobalLayoutListener(() -> recordMetrics(content,decor));
            content.setOnApplyWindowInsetsListener((view, insets) -> {
                int left, top, right, bottom, keyboard = 0;
                if (Build.VERSION.SDK_INT >= 30) {
                    Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                    left=bars.left; top=bars.top; right=bars.right; bottom=bars.bottom;
                    keyboard = insets.getInsets(WindowInsets.Type.ime()).bottom;
                } else {
                    left=insets.getSystemWindowInsetLeft(); top=insets.getSystemWindowInsetTop();
                    right=insets.getSystemWindowInsetRight(); bottom=insets.getSystemWindowInsetBottom();
                    if (insets.getDisplayCutout() != null) {
                        left=Math.max(left,insets.getDisplayCutout().getSafeInsetLeft());
                        top=Math.max(top,insets.getDisplayCutout().getSafeInsetTop());
                        right=Math.max(right,insets.getDisplayCutout().getSafeInsetRight());
                        bottom=Math.max(bottom,insets.getDisplayCutout().getSafeInsetBottom());
                    }
                }
                view.setPadding(left,top,right,Math.max(bottom,keyboard));
                bars[0]=left;bars[1]=top;bars[2]=right;bars[3]=bottom;
                view.post(() -> recordMetrics(view,decor));
                return Build.VERSION.SDK_INT >= 30 ? WindowInsets.CONSUMED
                        : insets.consumeSystemWindowInsets().consumeDisplayCutout();
            });
            content.requestApplyInsets();
        });
    }

    private static SharedPreferences preferences() {
        if (activity == null) throw new IllegalStateException("Android folder access is not ready.");
        return activity.getSharedPreferences("saavndl_destination",Activity.MODE_PRIVATE);
    }

    public static String getLayoutMetrics() { return metrics; }

    public static void finishStartup() { StartupSplash.ready(activity); }

    public static String getStartupStats() { return StartupSplash.stats(); }

    public static String getDestination() {
        try {
            JSONObject data=new JSONObject();
            data.put("uri",preferences().getString("uri",""));
            data.put("label",preferences().getString("label","Downloads"));
            String saved=preferences().getString("uri","");
            String path="Downloads";
            if (!saved.isEmpty()) {
                String id=DocumentsContract.getTreeDocumentId(Uri.parse(saved));
                path=id.startsWith("primary:") ? "Internal storage/"+id.substring(8) : "Selected storage/"+id.replace(':','/');
            }
            data.put("path",path);
            data.put("pending",choosing); data.put("error",folderError);
            return data.toString();
        } catch (Exception error) { throw new IllegalStateException(error.getMessage()); }
    }

    public static void chooseFolder() {
        if (choosing) return;
        choosing=true; folderError="";
        activity.runOnUiThread(() -> {
            try {
                Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
                String previous=preferences().getString("uri","");
                Uri initial=previous.isEmpty() ? Uri.parse("content://com.android.externalstorage.documents/document/primary%3ADocuments") : Uri.parse(previous);
                intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI,initial);
                activity.startActivityForResult(intent,FOLDER_REQUEST);
            } catch (Exception error) { choosing=false; folderError="Could not open the folder picker: "+error.getMessage(); }
        });
    }

    public static void useDefaultFolder() {
        String previous=preferences().getString("uri","");
        if (!previous.isEmpty()) {
            try { activity.getContentResolver().releasePersistableUriPermission(Uri.parse(previous),
                    Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION); }
            catch (Exception ignored) {}
        }
        preferences().edit().remove("uri").remove("label").apply();
        folderError=""; choosing=false;
    }

    @Override public void onActivityResult(int request,int result,Intent intent) {
        if (request != FOLDER_REQUEST) return;
        choosing=false;
        if (result != Activity.RESULT_OK || intent == null || intent.getData() == null) return;
        try {
            Uri tree=intent.getData();
            int flags=intent.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            if ((flags & Intent.FLAG_GRANT_WRITE_URI_PERMISSION) == 0)
                throw new SecurityException("The selected folder did not grant write access.");
            activity.getContentResolver().takePersistableUriPermission(tree,flags);
            Uri document=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
            String label=displayName(document);
            preferences().edit().putString("uri",tree.toString()).putString("label",label).apply();
            folderError="";
        } catch (Exception error) { folderError="Folder access was not saved: "+error.getMessage(); }
    }

    private static String displayName(Uri uri) {
        try (Cursor cursor=activity.getContentResolver().query(uri,
                new String[]{DocumentsContract.Document.COLUMN_DISPLAY_NAME},null,null,null)) {
            if (cursor != null && cursor.moveToFirst()) return cursor.getString(0);
        }
        return "Selected folder";
    }

    private static Uri childDirectory(Uri tree,Uri parent,String name) throws Exception {
        Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getDocumentId(parent));
        try (Cursor cursor=activity.getContentResolver().query(children,new String[]{
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE},null,null,null)) {
            if (cursor != null) while (cursor.moveToNext()) {
                if (name.equals(cursor.getString(1)) && DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2)))
                    return DocumentsContract.buildDocumentUriUsingTree(tree,cursor.getString(0));
            }
        }
        Uri created=DocumentsContract.createDocument(activity.getContentResolver(),parent,DocumentsContract.Document.MIME_TYPE_DIR,name);
        if (created == null) throw new IllegalStateException("Could not create the album folder.");
        return created;
    }

    public static String exportToFolder(String source,String subfolder,String mime) throws Exception {
        String chosen=preferences().getString("uri","");
        if (chosen.isEmpty()) throw new IllegalStateException("Select a custom folder first.");
        Uri tree=Uri.parse(chosen);
        Uri directory=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
        for (String part:subfolder.split("/")) {
            if (part.isEmpty()) continue;
            if (part.equals(".") || part.equals("..") || part.contains("\\")) throw new SecurityException("Invalid output folder.");
            directory=childDirectory(tree,directory,part);
        }
        File file=new File(source);
        ContentResolver resolver=activity.getContentResolver();
        Uri target=DocumentsContract.createDocument(resolver,directory,mime,file.getName());
        if (target == null) throw new IllegalStateException("The selected folder could not create a file.");
        try (FileInputStream input=new FileInputStream(file); OutputStream output=resolver.openOutputStream(target,"w")) {
            if (output == null) throw new IllegalStateException("The selected folder could not open the file.");
            byte[] buffer=new byte[65536]; int count;
            while ((count=input.read(buffer)) != -1) output.write(buffer,0,count);
            output.flush();
        } catch (Exception error) {
            try { DocumentsContract.deleteDocument(resolver,target); } catch (Exception ignored) {}
            throw error;
        }
        return displayName(target);
    }

    /** Explicit CI intent only; verifies the provider grant with a fixed disposable payload. */
    public static boolean checkCustomFolder() throws Exception {
        if (!activity.getIntent().getBooleanExtra("saavn_native_test",false))
            throw new SecurityException("Native test mode is disabled.");
        byte[] expected="SaavnDl custom folder check\n".getBytes(StandardCharsets.UTF_8);
        File source=File.createTempFile("saavndl-folder-check-",".txt",activity.getCacheDir());
        Uri found=null;
        ContentResolver resolver=activity.getContentResolver();
        try {
            try (FileOutputStream out=new FileOutputStream(source)) { out.write(expected); }
            String filename=exportToFolder(source.getAbsolutePath(),"","text/plain");
            Uri tree=Uri.parse(preferences().getString("uri",""));
            Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
            try (Cursor cursor=resolver.query(children,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME},null,null,null)) {
                if (cursor != null) while (cursor.moveToNext()) if (filename.equals(cursor.getString(1))) {
                    found=DocumentsContract.buildDocumentUriUsingTree(tree,cursor.getString(0)); break;
                }
            }
            if (found == null) throw new IllegalStateException("Custom output file could not be found.");
            try (InputStream input=resolver.openInputStream(found); ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
                if (input == null) throw new IllegalStateException("Custom output file could not be read.");
                byte[] buffer=new byte[1024]; int n;
                while ((n=input.read(buffer)) != -1) bytes.write(buffer,0,n);
                if (!Arrays.equals(expected,bytes.toByteArray())) throw new IllegalStateException("Custom output content did not match.");
            }
            return true;
        } finally {
            source.delete();
            if (found != null) DocumentsContract.deleteDocument(resolver,found);
        }
    }
}
