from gamecubby_api.utils.external import _escape_search_term


def test_igdb_search_terms_escape_quotes_and_backslashes():
    assert _escape_search_term('Game "Deluxe"') == 'Game \\"Deluxe\\"'
    assert _escape_search_term(r"C:\\Games") == r"C:\\\\Games"
