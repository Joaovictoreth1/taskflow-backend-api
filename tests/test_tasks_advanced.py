"""Tests for advanced task capabilities: priorities, due dates, filtering, and pagination."""

from tests.conftest import client


class TestTaskPriorityAndDueDate:
    def setup_method(self):
        resp = client.post("/projects", json={"name": "Sprint 1", "description": "Core features"})
        self.project_id = resp.json()["id"]

    def test_create_task_with_default_priority(self):
        resp = client.post(
            f"/projects/{self.project_id}/tasks",
            json={"title": "Default Priority Task"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["priority"] == "medium"
        assert data["status"] == "todo"
        assert data["due_date"] is None

    def test_create_task_with_urgent_priority_and_due_date(self):
        due = "2026-12-31T23:59:59Z"
        resp = client.post(
            f"/projects/{self.project_id}/tasks",
            json={
                "title": "Fix Critical Production Bug",
                "priority": "urgent",
                "due_date": due,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["priority"] == "urgent"
        assert data["due_date"] is not None

    def test_create_task_invalid_priority_rejected(self):
        resp = client.post(
            f"/projects/{self.project_id}/tasks",
            json={"title": "Invalid Priority Task", "priority": "super-critical"},
        )
        assert resp.status_code == 422

    def test_clear_task_due_date(self):
        task_resp = client.post(
            f"/projects/{self.project_id}/tasks",
            json={"title": "Temporary Due Date", "due_date": "2026-11-20T12:00:00Z"},
        )
        task_id = task_resp.json()["id"]
        assert task_resp.json()["due_date"] is not None

        # Update setting due_date to null
        update_resp = client.patch(f"/tasks/{task_id}", json={"due_date": None})
        assert update_resp.status_code == 200
        assert update_resp.json()["due_date"] is None

    def test_update_task_priority_and_due_date(self):
        task_resp = client.post(
            f"/projects/{self.project_id}/tasks",
            json={"title": "Routine Maintenance", "priority": "low"},
        )
        task_id = task_resp.json()["id"]

        # Escalate priority to high
        update_resp = client.patch(
            f"/tasks/{task_id}",
            json={"priority": "high", "status": "in_progress"},
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["priority"] == "high"
        assert data["status"] == "in_progress"


class TestTaskFilteringAndPagination:
    def setup_method(self):
        # Create Project A
        p_a = client.post("/projects", json={"name": "Frontend Web App"}).json()
        self.p_a_id = p_a["id"]

        # Create Project B
        p_b = client.post("/projects", json={"name": "Mobile iOS App"}).json()
        self.p_b_id = p_b["id"]

        # Seed 5 tasks in Project A
        client.post(
            f"/projects/{self.p_a_id}/tasks",
            json={"title": "Setup React router", "status": "done", "priority": "high"},
        )
        client.post(
            f"/projects/{self.p_a_id}/tasks",
            json={"title": "Implement login screen", "status": "in_progress", "priority": "urgent"},
        )
        client.post(
            f"/projects/{self.p_a_id}/tasks",
            json={"title": "Configure Tailwind CSS", "status": "done", "priority": "low"},
        )
        client.post(
            f"/projects/{self.p_a_id}/tasks",
            json={"title": "Write unit tests for UI", "status": "todo", "priority": "medium"},
        )
        client.post(
            f"/projects/{self.p_a_id}/tasks",
            json={"title": "Optimize bundle size", "status": "todo", "priority": "medium"},
        )

        # Seed 2 tasks in Project B
        client.post(
            f"/projects/{self.p_b_id}/tasks",
            json={"title": "SwiftUI Navigation stack", "status": "todo", "priority": "high"},
        )
        client.post(
            f"/projects/{self.p_b_id}/tasks",
            json={"title": "Push notifications APNS", "status": "in_progress", "priority": "urgent"},
        )

    def test_filter_tasks_by_status(self):
        resp = client.get("/tasks?status=done")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["status"] == "done"

    def test_filter_tasks_by_priority(self):
        resp = client.get("/tasks?priority=urgent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["priority"] == "urgent"

    def test_filter_tasks_by_project_id(self):
        resp = client.get(f"/tasks?project_id={self.p_b_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["project_id"] == self.p_b_id

    def test_filter_tasks_by_search_keyword(self):
        resp = client.get("/tasks?search=router")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert "router" in data["items"][0]["title"].lower()

    def test_filter_tasks_by_combined_status_and_priority(self):
        resp = client.get("/tasks?status=in_progress&priority=urgent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["status"] == "in_progress"
            assert item["priority"] == "urgent"

    def test_filter_tasks_empty_result(self):
        resp = client.get("/tasks?search=nonexistent_query_xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_pagination_envelope_structure(self):
        resp = client.get("/tasks?page=1&size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert "pages" in data
        assert data["page"] == 1
        assert data["size"] == 3
        assert len(data["items"]) == 3
        assert data["total"] == 7
        assert data["pages"] == 3  # ceil(7 / 3) = 3


class TestProjectPagination:
    def test_search_projects_by_keyword(self):
        client.post("/projects", json={"name": "Alpha Machine Learning Pipeline"})
        client.post("/projects", json={"name": "Beta Web Portal"})

        resp = client.get("/projects?search=Machine")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "Machine Learning" in data[0]["name"]

    def test_paginated_projects(self):
        for i in range(12):
            client.post("/projects", json={"name": f"Enterprise Project {i:02d}"})

        resp = client.get("/projects/paginated?page=1&size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 12
        assert data["page"] == 1
        assert data["size"] == 5
        assert data["pages"] == 3
        assert len(data["items"]) == 5

        # Check page 3 (remaining 2)
        resp3 = client.get("/projects/paginated?page=3&size=5")
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert len(data3["items"]) == 2
