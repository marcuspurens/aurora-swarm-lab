from app.modules.scrape.readable_text import extract


def test_extract_strips_script_and_normalizes():
    html = """
    <html>
      <head>
        <title>Title</title>
        <script>bad()</script>
      </head>
      <body>
        <h1>Hello</h1>
        <p>World</p>
      </body>
    </html>
    """
    text = extract(html)
    assert text == "Hello World"
