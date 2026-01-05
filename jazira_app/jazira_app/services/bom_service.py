from typing import Dict, List, Optional
from dataclasses import dataclass

import frappe


@dataclass
class RawMaterial:
    """Raw material item from BOM."""
    item_code: str
    qty: float
    uom: str


class BOMService:
    """
    Service for BOM operations.
    
    Handles:
    - Finding default BOM for items
    - Exploding BOM to get raw materials
    - Calculating required quantities
    """
    
    def get_default_bom(self, item_code: str) -> Optional[str]:
        """
        Get default active BOM for an item.
        
        Args:
            item_code: Item code
            
        Returns:
            BOM name or None if not found
        """
        return frappe.db.get_value(
            "BOM",
            {
                "item": item_code,
                "is_default": 1,
                "is_active": 1,
                "docstatus": 1
            },
            "name"
        )
    
    def get_raw_materials(self, bom_name: str, qty: float) -> List[RawMaterial]:
        """
        Get raw materials from BOM with calculated quantities.
        
        Args:
            bom_name: BOM document name
            qty: Required quantity of finished item
            
        Returns:
            List of RawMaterial objects
        """
        if not bom_name or qty <= 0:
            return []
        
        # Get BOM items
        bom_items = self._get_bom_items(bom_name)
        
        # Get BOM base quantity
        bom_qty = frappe.db.get_value("BOM", bom_name, "quantity") or 1
        
        # Calculate required quantities
        materials = []
        for item in bom_items:
            required_qty = (item["stock_qty"] / bom_qty) * qty
            
            materials.append(RawMaterial(
                item_code=item["item_code"],
                qty=required_qty,
                uom=item["stock_uom"] or item["uom"]
            ))
        
        return materials
    
    def _get_bom_items(self, bom_name: str) -> List[Dict]:
        """Get BOM items using query builder."""
        from frappe.query_builder import DocType
        
        BOMItem = DocType("BOM Item")
        
        return (
            frappe.qb.from_(BOMItem)
            .select(
                BOMItem.item_code,
                BOMItem.qty,
                BOMItem.uom,
                BOMItem.stock_qty,
                BOMItem.stock_uom
            )
            .where(BOMItem.parent == bom_name)
            .run(as_dict=True)
        )
    
    def categorize_items_by_bom(self, items: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Categorize items by BOM availability.
        
        Args:
            items: List of items with 'item_code' key
            
        Returns:
            {
                "with_bom": items that have BOM,
                "without_bom": items without BOM
            }
        """
        with_bom = []
        without_bom = []
        
        for item in items:
            item_code = item.get("item_code")
            if not item_code:
                continue
            
            bom = self.get_default_bom(item_code)
            
            if bom:
                item["bom"] = bom
                item["has_bom"] = True
                with_bom.append(item)
            else:
                item["has_bom"] = False
                without_bom.append(item)
        
        return {
            "with_bom": with_bom,
            "without_bom": without_bom
        }


# Singleton instance
bom_service = BOMService()
