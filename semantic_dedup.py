import re
import time
from typing import Dict, List, Optional, Set, Tuple

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "must", "can", "could",
    "it", "its", "as", "that", "this", "these", "those", "says", "said", "says",
    "news", "latest", "report", "live", "update", "updates", "today", "market"
}

def clean_tokens(text: str) -> Set[str]:
    """Extracts normalized alphanumeric token set from title/text, filtering stopwords."""
    if not text:
        return set()
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    tokens = [w for w in cleaned.split() if len(w) >= 3 and w not in STOPWORDS]
    return set(tokens)

def extract_financial_entities(text: str) -> Set[str]:
    """
    Extracts key quantitative & company entities (e.g. 'q1', 'q2', 'pat', '6500cr', '5.1%', 'tcs', 'hdfc').
    """
    entities = set()
    text_lower = text.lower()
    
    # Financial metrics & periods
    for m in re.findall(r'\b(q[1-4]|fy\d{2,4}|pat|ebitda|revenue|dividend|buyback|split|repo|cpi|iip|fomc|gdp|crude|brent|nifty|sensex)\b', text_lower):
        entities.add(m)
        
    # Percentages and monetary numbers
    for p in re.findall(r'(\d+\.?\d*%)', text_lower):
        entities.add(p)
    for c in re.findall(r'(₹?\d+[\d,]*\.?\d*\s*(?:cr|crore|lakh|b|m|k))', text_lower):
        entities.add(re.sub(r'[^a-z0-9]', '', c))

    return entities

class SemanticNewsClusterer:
    """
    Maintains a rolling in-memory window of recent news items (e.g. past 60-90 minutes).
    Performs fast token Jaccard similarity & entity-overlap checks to cluster syndicated news stories.
    """
    def __init__(self, window_seconds: int = 5400, similarity_threshold: float = 0.55):
        self.window_seconds = window_seconds
        self.similarity_threshold = similarity_threshold
        # List of clusters: { "master": item, "tokens": set, "entities": set, "sources": [{"source": ..., "link": ...}], "created_at": float }
        self.clusters: List[Dict] = []

    def _prune_old_clusters(self):
        cutoff = time.time() - self.window_seconds
        self.clusters = [c for c in self.clusters if c["created_at"] >= cutoff]

    def check_duplicate_or_cluster(self, item: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Checks if item matches an existing cluster.
        If it's a duplicate/syndicated story:
          - Appends source to the cluster's additional sources
          - Returns (True, master_item)
        If it's a unique new story:
          - Registers a new cluster
          - Returns (False, None)
        """
        self._prune_old_clusters()

        title = item.get("title", "")
        summary = item.get("summary", "")
        full_text = f"{title} {summary}"

        tokens = clean_tokens(title)
        entities = extract_financial_entities(full_text)

        if not tokens:
            return False, None

        best_match = None
        highest_score = 0.0

        for c in self.clusters:
            c_tokens = c["tokens"]
            c_entities = c["entities"]

            # 1. Jaccard Token Similarity
            intersection = tokens.intersection(c_tokens)
            union = tokens.union(c_tokens)
            jaccard = len(intersection) / len(union) if union else 0.0

            # 2. Entity Overlap
            entity_overlap = len(entities.intersection(c_entities)) if (entities and c_entities) else 0

            # Combined score: Jaccard + entity bonus
            # If stories share key company token (or 2+ common tokens) AND identical quantitative entities (like 'q2' + '6500cr'), they are duplicates!
            score = jaccard
            if len(intersection) >= 2 and entity_overlap >= 1:
                score += 0.35
            elif len(intersection) >= 1 and entity_overlap >= 2:
                score += 0.40
            elif entity_overlap >= 3:
                score += 0.30

            if score > highest_score and score >= self.similarity_threshold:
                highest_score = score
                best_match = c

        if best_match:
            # Duplicate / syndicated story detected!
            source_info = {
                "source": item.get("source", "Wire"),
                "link": item.get("link", "#"),
                "timestamp": item.get("timestamp", "")
            }
            # Append source if not already present
            existing_sources = [s["source"] for s in best_match["sources"]]
            if source_info["source"] not in existing_sources:
                best_match["sources"].append(source_info)
                master = best_match["master"]
                master["other_sources"] = best_match["sources"]

            return True, best_match["master"]

        # If unique, create new cluster
        new_cluster = {
            "master": item,
            "tokens": tokens,
            "entities": entities,
            "sources": [{"source": item.get("source", "Wire"), "link": item.get("link", "#"), "timestamp": item.get("timestamp", "")}],
            "created_at": time.time()
        }
        item["other_sources"] = new_cluster["sources"]
        self.clusters.append(new_cluster)
        return False, None

semantic_clusterer = SemanticNewsClusterer()
