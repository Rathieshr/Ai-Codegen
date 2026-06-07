import unittest

from backend.workflow.work_item_drafts import build_story_drafts_from_epic_or_feature, flatten_drafts


class WorkItemDraftQualityTests(unittest.TestCase):
    def test_mobile_commerce_epic_generates_specific_feature_story_details(self) -> None:
        drafts = build_story_drafts_from_epic_or_feature(
            {
                "id": 901,
                "type": "Epic",
                "title": "Launch iOS & Android Mobile E-Commerce Applications",
                "tags": ["iOS", "Android"],
            },
            source_stage="story_generation",
            flows=["checkout"],
            variants=[],
            fields=["delivery_address", "payment_method"],
            include_ui=True,
            count=4,
            feature_seeds=[],
        )

        flat = flatten_drafts(drafts)
        feature_titles = [draft["title"] for draft in flat if draft["draft_type"] == "Feature"]
        story_drafts = [draft for draft in flat if draft["draft_type"] == "User Story"]

        self.assertIn("Launch iOS & Android Mobile E-Commerce Applications: Mobile Shopping Experience", feature_titles)
        self.assertTrue(story_drafts)
        self.assertFalse(any("Story 1" in draft["title"] or "Story Slice" in draft["title"] for draft in story_drafts))
        self.assertTrue(all(draft["description"] for draft in story_drafts))
        self.assertTrue(all(len(draft["acceptance_criteria"]) >= 3 for draft in story_drafts))
        self.assertIn("product", " ".join(story_drafts[0]["acceptance_criteria"]).lower())


if __name__ == "__main__":
    unittest.main()
