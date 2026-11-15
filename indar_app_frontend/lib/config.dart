/// Backend base URL.
///
/// Defaults to 10.0.2.2, which is how the Android emulator reaches the
/// backend running on your computer. On a real phone, pass your computer's
/// LAN IP when running:
///
///   flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);
