import os, psycopg2

DB_URL = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")

def load_list(path, label):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                yield url, label

def main():
    rows = []
    rows += list(load_list("/workspace/data/raw_urls/dandelion.txt", "dandelion"))
    rows += list(load_list("/workspace/data/raw_urls/grass.txt", "grass"))
    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS plants_data(
            url_source TEXT PRIMARY KEY,
            url_s3 TEXT,
            label TEXT CHECK (label IN ('dandelion','grass'))
        );
        """)
        for url, label in rows:
            cur.execute(
                "INSERT INTO plants_data(url_source, url_s3, label) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (url, None, label))
    print(f"seeded {len(rows)} urls")

if __name__ == "__main__":
    main()
