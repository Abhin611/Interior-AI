/// App settings, read at build time from env.json:
///
///   flutter run --dart-define-from-file=env.json
///
/// Copy env.example.json to env.json and fill in your own values.

/// Backend base URL. 10.0.2.2 is how the Android emulator reaches the
/// backend running on your computer. On a real phone use your PC's LAN IP,
/// e.g. http://192.168.1.10:8000
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

/// Supabase project URL, e.g. https://abcdefgh.supabase.co
const String supabaseUrl = String.fromEnvironment('SUPABASE_URL');

/// Supabase anon (public) key. Safe to ship in the app.
const String supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

bool get isConfigured => supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;
