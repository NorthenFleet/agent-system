from services.product_service import ProductRegistryService


def test_registry_seeds_core_products(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    registry = service.get_registry()
    product_ids = {row["id"] for row in registry["products"]}

    assert registry["schema"] == "openclaw.product-registry"
    assert {"openclaw-3021", "ai-planning-5130", "one-sim"}.issubset(product_ids)
    assert (tmp_path / "product-registry.json").exists()


def test_registry_product_lifecycle(tmp_path):
    service = ProductRegistryService(str(tmp_path / "product-registry.json"))
    created = service.upsert_product("report-engine", {
        "name": "报告生成产品",
        "kind": "service",
        "status": "planning",
        "capabilities": ["报告生成"],
    })

    assert created["id"] == "report-engine"
    assert service.get_product("report-engine")["capabilities"] == ["报告生成"]
    assert service.delete_product("report-engine") is True
    assert service.get_product("report-engine") is None
