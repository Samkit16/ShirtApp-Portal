import streamlit as st
from sqlalchemy import text
import pandas as pd
import time
import json
import requests
import base64

def upload_to_imgbb(image_file):
    # Replace the string below with your actual API key from imgbb.com
    api_key = "ec667a2de584a4696d4e2a1f1a85ce2f" 
    url = "https://api.imgbb.com/1/upload"
    
    try:
        # Convert the uploaded file to base64 for the API
        image_data = base64.b64encode(image_file.read()).decode('utf-8')
        payload = {
            "key": api_key,
            "image": image_data,
        }
        res = requests.post(url, payload)
        if res.status_code == 200:
            return res.json()['data']['url']
        else:
            st.error(f"ImgBB Error: {res.json().get('error', {}).get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None
      
st.set_page_config(page_title="Admin Dashboard", layout="wide")
st.title("👔 Wholesale Admin Dashboard")

# Connect to Database
conn = st.connection("postgresql", type="sql")

tab1, tab2, tab3, tab4 = st.tabs(["📦 View Inventory", "✨ New Design", "➕ Add Stock", "🚚 Orders & Cleanup"])

# --- TAB 1: VIEW INVENTORY ---
with tab1:
    st.subheader("Current Stock Levels")
    try:
        query = """
            SELECT d.design_name, d.category, d.price, v.color, v.size, v.stock_quantity 
            FROM shirt_designs d
            LEFT JOIN shirt_variants v ON d.design_id = v.design_id
            ORDER BY d.design_name, v.color, v.size;
        """
        df = conn.query(query, ttl=0)
        if df.empty:
            st.info("Your inventory is currently empty.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error loading inventory: {e}")

# --- TAB 2: CREATE A NEW DESIGN ---
with tab2:
    st.subheader("Step 1: Create a New Shirt Profile")
    st.info("Fill in the details and upload images for the catalog.")
    
    with st.form("new_design_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Design Name (e.g., Classic Checkered)")
            category = st.selectbox("Category", ["Formal", "Casual", "Party Wear", "Printed"])
        with col2:
            price = st.number_input("Price per piece (₹)", min_value=0.0, format="%.2f")
            moq = st.number_input("Minimum Order Quantity (MOQ)", min_value=1, value=5, step=1)
        
        # --- THE MULTIPLE IMAGE UPLOADER ---
        uploaded_files = st.file_uploader("Upload Catalog Images (First image will be the primary display)", 
                                          type=["jpg", "png", "jpeg"], 
                                          accept_multiple_files=True) # <-- This unlocks multiple uploads!
            
        submit_button = st.form_submit_button("Save Design & Images 🚀")
        
        if submit_button:
            if not name:
                st.error("Please enter a Design Name.")
            elif not uploaded_files:
                st.error("Please upload at least one image for the catalog.")
            else:
                try:
                    with conn.session as s:
                        # 1. Insert into shirt_designs and get the new ID first
                        query = text("""
                            INSERT INTO shirt_designs (design_name, category, price, moq, is_active) 
                            VALUES (:name, :category, :price, :moq, TRUE)
                            RETURNING design_id
                        """)
                        result = s.execute(query, {"name": name, "category": category, "price": price, "moq": moq})
                        new_design_id = result.fetchone()[0]
                        
                        # 2. Upload ALL images to ImgBB and save to database
                        with st.spinner(f"Uploading {len(uploaded_files)} images..."):
                            for index, file in enumerate(uploaded_files):
                                image_url = upload_to_imgbb(file)
                                
                                if image_url:
                                    # Make the first uploaded image the primary one
                                    is_primary = True if index == 0 else False
                                    
                                    img_query = text("""
                                        INSERT INTO shirt_images (design_id, image_url, is_primary) 
                                        VALUES (:did, :url, :is_primary)
                                    """)
                                    s.execute(img_query, {"did": new_design_id, "url": image_url, "is_primary": is_primary})
                                else:
                                    st.error(f"Failed to upload {file.name}")
                                    
                        s.commit()
                        
                    st.success(f"✅ Successfully added '{name}' with {len(uploaded_files)} image(s)!")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Database Error: {e}")
# --- TAB 3: ADD STOCK TO A DESIGN ---
with tab3:
    st.subheader("Step 2: Add Colors & Sizes to a Design")
    try:
        # Fetch existing designs for the dropdown
        designs_df = conn.query("SELECT design_id, design_name FROM shirt_designs ORDER BY design_name ASC;", ttl=0)
        
        if designs_df.empty:
            st.warning("Please create a Design in Step 1 first.")
        else:
            design_dict = dict(zip(designs_df["design_name"], designs_df["design_id"]))
            
            with st.form("add_stock_form", clear_on_submit=True):
                selected_design = st.selectbox("Select Design", list(design_dict.keys()))
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    color = st.text_input("Color (e.g., Navy Blue)")
                with col2:
                    # Changed to multiselect and removed 'S'
                    size_choices = st.multiselect("Select Size(s)", ["All Sizes", "M", "L", "XL", "XXL"])
                with col3:
                    qty = st.number_input("Stock Quantity (per selected size)", min_value=1, step=1)
                    
                submit_stock = st.form_submit_button("Add Stock")
                
                if submit_stock:
                    if not color:
                        st.error("Please enter a color.")
                    elif not size_choices:
                        st.error("Please select at least one size.")
                    else:
                        d_id = design_dict[selected_design]
                        available_sizes = ["M", "L", "XL", "XXL"]
                        
                        # If "All Sizes" is picked anywhere in the multiselect, use all 4 sizes
                        if "All Sizes" in size_choices:
                            sizes_to_add = available_sizes
                        else:
                            sizes_to_add = size_choices
                        
                        try:
                            with conn.session as s:
                                for sz in sizes_to_add:
                                    query = text("""
                                        INSERT INTO shirt_variants (design_id, color, size, stock_quantity)
                                        VALUES (:did, :color, :size, :qty)
                                    """)
                                    s.execute(query, {"did": int(d_id), "color": color, "size": sz, "qty": qty})
                                s.commit()
                                
                            st.success(f"✅ Successfully added {qty} units for size(s) {', '.join(sizes_to_add)} in {color} to {selected_design}.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Database Error: {e}")
    except Exception as e:
        st.error(f"Error loading designs: {e}")
# --- TAB 4: ORDERS & CLEANUP ---
with tab4:
    # Section A: Actionable Pending Orders
    st.subheader("📦 Pending Orders (Needs Dispatch)")
    try:
        pending_df = conn.query("SELECT * FROM orders WHERE order_status = 'Pending' ORDER BY order_date ASC;", ttl=0)
        
        if pending_df.empty:
            st.success("🎉 All caught up! No pending orders right now.")
        else:
            for index, row in pending_df.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 3, 1.5])
                    with col1:
                        order_time = pd.to_datetime(row['order_date']).strftime('%Y-%m-%d %I:%M %p')
                        st.write(f"**Order #{row['order_id']}**")
                        st.write(f"👤 {row['retailer_name']}")
                        st.write(f"📞 {row['retailer_phone']}")
                        st.write(f"🕒 {order_time}")
                        st.write(f"💰 ₹{row['total_value']}")
                        
                    with col2:
                        st.write("**Order Details:**")
                        cart_data = json.loads(row['order_summary']) if isinstance(row['order_summary'], str) else row['order_summary']
                        for v_id, item in cart_data.items():
                            st.write(f"- {item['qty']}x {item['name']} ({item['color']}, Size {item['size']})")
                            
                    with col3:
                        st.write("")
                        # Button 1: Standard Dispatch (Deducts stock levels)
                        if st.button("🚚 Dispatch", key=f"btn_disp_{row['order_id']}", type="primary", use_container_width=True):
                            with conn.session as s:
                                for v_id, item in cart_data.items():
                                    query = text("UPDATE shirt_variants SET stock_quantity = GREATEST(stock_quantity - :qty, 0) WHERE variant_id = :vid")
                                    s.execute(query, {"qty": item['qty'], "vid": int(v_id)})
                                update_order = text("UPDATE orders SET order_status = 'Dispatched' WHERE order_id = :oid")
                                s.execute(update_order, {"oid": row['order_id']})
                                s.commit()
                            st.success(f"✅ Order Dispatched!")
                            time.sleep(1)
                            st.rerun()
                        
                        # Button 2: New Delete Feature (Removes order record entirely, stock stays untouched)
                        if st.button("🗑️ Delete (Keep Stock)", key=f"btn_del_pend_{row['order_id']}", type="secondary", use_container_width=True):
                            with conn.session as s:
                                delete_query = text("DELETE FROM orders WHERE order_id = :oid")
                                s.execute(delete_query, {"oid": row['order_id']})
                                s.commit()
                            st.warning(f"🗑️ Order #{row['order_id']} deleted. Inventory count was not changed.")
                            time.sleep(1)
                            st.rerun()
                            
    except Exception as e:
        st.error(f"Could not load pending orders: {e}")

    st.markdown("---")
    
    # Section B: View Order History with Cleanup Option
    st.subheader("📥 Dispatched Order History")
    try:
        history_df = conn.query("SELECT order_id, order_date, retailer_name, retailer_phone, total_value, order_summary FROM orders WHERE order_status = 'Dispatched' ORDER BY order_date DESC;", ttl=0)
        if history_df.empty:
            st.info("No dispatched orders in history.")
        else:
            # Display history for admin preview
            display_history = history_df.copy()
            display_history['order_date'] = pd.to_datetime(display_history['order_date']).dt.strftime('%Y-%m-%d %I:%M %p')
            
            def format_cart(cart_data):
                try:
                    cart_dict = json.loads(cart_data) if isinstance(cart_data, str) else cart_data
                    items = [f"{item['qty']}x {item['name']} ({item['color']}, {item['size']})" for key, item in cart_dict.items()]
                    return " | ".join(items)
                except:
                    return "Error reading cart"
                    
            display_history['order_summary'] = display_history['order_summary'].apply(format_cart)
            st.dataframe(display_history, use_container_width=True, hide_index=True)
            
            # Allow deleting historical logs quietly too
            with st.expander("Clear Records From History Log"):
                order_to_clear = st.selectbox("Select History Order ID to Remove", history_df['order_id'].unique())
                if st.button("Delete History Entry Permanently", type="primary"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM orders WHERE order_id = :oid"), {"oid": int(order_to_clear)})
                        s.commit()
                    st.success(f"✅ Order #{order_to_clear} cleared from history logs.")
                    time.sleep(1)
                    st.rerun()
                    
    except Exception as e:
        st.error(f"Could not load order history: {e}")

    st.markdown("---")
    
    # Section C: Delete Inventory
    st.subheader("🗑️ Danger Zone: Delete Inventory")
    try:
        designs_for_deletion = conn.query("SELECT design_id, design_name FROM shirt_designs ORDER BY design_name ASC;", ttl=0)
        if not designs_for_deletion.empty:
            del_dict = dict(zip(designs_for_deletion["design_name"], designs_for_deletion["design_id"]))
            with st.form("delete_design_form"):
                shirt_to_delete = st.selectbox("Select Design to Permanently Delete", list(del_dict.keys()))
                st.warning("⚠️ Warning: This will permanently delete the design and all stock.")
                submit_delete = st.form_submit_button("Delete Permanently", type="primary")
                if submit_delete:
                    del_id = del_dict[shirt_to_delete]
                    with conn.session as s:
                        s.execute(text("DELETE FROM shirt_designs WHERE design_id = :id"), {"id": int(del_id)})
                        s.commit()
                    st.success(f"✅ Permanently deleted '{shirt_to_delete}'.")
                    time.sleep(1)
                    st.rerun()
    except Exception as e:
        pass
