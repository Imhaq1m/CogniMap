/**
 * Level 2: Understand — Paraphrase definitions, semantic similarity check.
 */

const Level2 = {
  async validateParaphrase(original, paraphrase) {
    return API.post("/api/level2/validate-paraphrase", {
      original,
      paraphrase,
      participant_id: "P01",
    });
  },
};
