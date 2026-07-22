"""
Production hardening that is easy to get wrong and expensive to get wrong.

These assert the *behaviour* the settings in config/settings.py are meant to
produce, rather than re-reading the values back, because the values are only
applied when DEBUG is off and the suite necessarily runs with it on.
"""

from django.test import SimpleTestCase, override_settings

PRODUCTION_SECURITY = dict(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_HSTS_SECONDS=31536000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
)

# Short enough to be rejected before any geocoder call, so these exercise
# middleware without reaching the network.
A_URL = "/api/locations/search/?q=de"


@override_settings(**PRODUCTION_SECURITY)
class ProxyTerminatedTlsTests(SimpleTestCase):
    def test_request_forwarded_as_https_is_served_not_redirected(self):
        """
        The redirect loop that takes the site down.

        Render terminates TLS at its edge and forwards plain HTTP, so Django
        sees an insecure request. With SECURE_SSL_REDIRECT on and no
        SECURE_PROXY_SSL_HEADER it answers every request with a redirect to the
        https URL the browser already used — for ever. SECURE_PROXY_SSL_HEADER
        is what lets it recognise the original scheme.
        """
        response = self.client.get(A_URL, headers={"x-forwarded-proto": "https"})

        self.assertEqual(response.status_code, 200)

    def test_plain_http_request_is_redirected_to_https(self):
        response = self.client.get(A_URL)

        self.assertEqual(response.status_code, 301)
        self.assertTrue(
            response["Location"].startswith("https://"),
            f"Expected an https redirect, got {response['Location']!r}",
        )

    def test_hsts_is_advertised_on_secure_requests(self):
        response = self.client.get(A_URL, headers={"x-forwarded-proto": "https"})

        policy = response.get("Strict-Transport-Security", "")
        self.assertIn("max-age=31536000", policy)
        self.assertIn("includeSubDomains", policy)
        self.assertIn("preload", policy)


class SecretKeyGuardTests(SimpleTestCase):
    def test_production_refuses_the_committed_development_key(self):
        """
        The dev key is in the repository, so anyone with a copy could forge
        session cookies and CSRF tokens. A missing SECRET_KEY is silent — the
        default just applies — so the failure has to be made loud.
        """
        settings_source = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "config" / "settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("if not DEBUG and SECRET_KEY == DEV_SECRET_KEY:", settings_source)
        self.assertIn("raise ImproperlyConfigured(", settings_source)
