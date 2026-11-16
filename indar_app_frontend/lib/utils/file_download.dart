// Saves bytes as a file download. Real implementation on the web; other
// platforms use the gallery / documents folder code in GeneratedPage.
export 'file_download_stub.dart'
    if (dart.library.js_interop) 'file_download_web.dart';
