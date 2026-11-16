import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'providers/image_provider.dart';
import 'providers/theme_provider.dart';
import 'pages/onboarding_page.dart';
import 'pages/home_page.dart';
import 'services/auth_service.dart';
import 'config.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (!isConfigured) {
    runApp(const _MissingConfigApp());
    return;
  }

  await Supabase.initialize(url: supabaseUrl, anonKey: supabaseAnonKey);

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ImageProviderModel()),
        ChangeNotifierProvider(create: (_) => ThemeProviderModel()),
      ],
      child: const MyApp(),
    ),
  );
}

final supabase = Supabase.instance.client;

/// Shown when the app was started without env.json, instead of crashing.
class _MissingConfigApp extends StatelessWidget {
  const _MissingConfigApp();

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        body: Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text(
              'Supabase is not configured.\n\n'
              'Copy env.example.json to env.json, fill in your keys, then run:\n'
              'flutter run --dart-define-from-file=env.json',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      ),
    );
  }
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: const _AuthGate(),
    );
  }
}

class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  bool? _isLoggedIn;

  @override
void initState() {
  super.initState();
  
  // 1. Check initial session immediately
  final initialSession = supabase.auth.currentSession;
  _isLoggedIn = initialSession != null;

  // 2. Listen for any subsequent changes
  supabase.auth.onAuthStateChange.listen((data) {
    if (!mounted) return;
    
    final Session? session = data.session;
    
    setState(() {
      // If session is NOT null, user is logged in.
      _isLoggedIn = session != null;
    });

    // Login/Register are pushed on top of the gate; clear them so the Home
    // (or Onboarding after sign out) page underneath becomes visible.
    // Only on real sign in / out, never on token refresh.
    if (data.event == AuthChangeEvent.signedIn ||
        data.event == AuthChangeEvent.signedOut) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
      });
    }

    if (data.event == AuthChangeEvent.signedIn) {
      AuthService.syncWithBackend();
    }
  });
}

  @override
  Widget build(BuildContext context) {
    // Still waiting for initial session check
    if (_isLoggedIn == null) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: CircularProgressIndicator(color: Colors.white),
        ),
      );
    }

    if (_isLoggedIn == true) {
      return const HomePage();
    }

    return const OnboardingPage();
  }
}



