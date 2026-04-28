import streamlit as st
from sqlalchemy import text
import pandas as pd
import time
import cloudinary
import cloudinary.uploader

# Connect to the Cloud Database
conn = st.connection("postgresql", type="sql")

# Connect to Cloudinary using your secrets file
cloudinary.config(
    cloud_name = st.secrets["cloudinary"]["cloud_name"],
    api_key = st.secrets["cloudinary"]["api_key"],
    api_secret = st.secrets["cloudinary"]["api_secret"],
    secure = True
)

st.set_page_config(page_title="B2B Shirt Admin", layout="wide")
st.title("👔 Admin Panel: Inventory Management")

# --- ADDED TAB 4 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Live Dashboard", "➕ Create New Design", "⚙️ Manage Photos & Stock", "📥 Orders & Cleanup"])

# --- TAB 1: EXECUTIVE DASHBOARD ---
with tab1:
    st.subheader("Inventory Overview")
    try:
        total_designs = conn.query("SELECT COUNT(*) FROM shirt_designs;", ttl=0).iloc[0,0]
        total_stock_df = conn.query("SELECT SUM(stock_quantity) FROM shirt_variants;", ttl=0)
        total_stock = total_stock_df.iloc[0,0] if not pd.isna(total_stock_df.iloc[0,0]) else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Unique Designs", total_designs)
        col2.metric("Total Pieces in Stock", int(total_stock))
        
        st.markdown("---")
        st.write("**Detailed Stock Breakdown:**")
        
        full_inventory_query = """
            SELECT d.design_name, d.category, d.price, v.color, v.size, v.stock_quantity 
            FROM shirt_designs d
            LEFT JOIN shirt_variants v ON d.design_id = v.design_id
            ORDER BY d.design_name, v.color;
        """
        inventory_df = conn.query(full_inventory_query, ttl=0)
        
        if inventory_df.empty:
            st.info("Your inventory is currently empty. Add a design in the next tab!")
        else:
            def highlight_zero(val):
                color = '#ffcccc' if val == 0 else ''
                return f'background-color: {color}'
            st.dataframe(inventory_df.style.map(highlight_zero, subset=['stock_quantity']), use_container_width=True)

    except Exception as e:
        st.error(f"Could not load dashboard data: {e}")

# --- TAB 2: CREATE A NEW DESIGN ---
with tab2:
    st.subheader("Step 1: Create a New Shirt Profile")
    with st.form("new_design_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Design Name (e.g., Classic Checkered)")
            category = st.selectbox("Category", ["Formal", "Casual", "Party Wear", "Printed"])
        with col2:
            price = st.number_input("Price per piece (₹)", min_value=0.0, format="%.2f")
            moq = st.number_input("Minimum Order Quantity (MOQ)", min_value=1, step=1)
            
        submit_button = st.form_submit_button("Save Design to Database")
        
        if submit_button:
            if name:
                query = text("""
                    INSERT INTO shirt_designs (design_name, category, price, moq) 
                    VALUES (:name, :category, :price, :moq)
                """)
                with conn.session as s:
                    s.execute(query, {"name": name, "category": category, "price": price, "moq": moq})
                    s.commit()
                
                st.success(f"✅ Successfully added '{name}'!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Please enter a Design Name before saving.")

# --- TAB 3: MANAGE PHOTOS & STOCK ---
with tab3:
    st.subheader("Step 2: Add Live Stock & Photos")
    try:
        designs_df = conn.query("SELECT design_id, design_name FROM shirt_designs ORDER BY design_id DESC;", ttl=0)
        
        if not designs_df.empty:
            design_dict = dict(zip(designs_df["design_name"], designs_df["design_id"]))
            
            selected_shirt = st.selectbox("👉 Select a Shirt to Manage", list(design_dict.keys()))
            design_id = design_dict[selected_shirt]
            
            st.markdown("---")
            col_left, col_right = st.columns(2)
            
            # Left Side: Add Stock
            with col_left:
                st.write("**📦 Add Stock Variants**")
                with st.form("add_stock_form", clear_on_submit=True):
                    color = st.text_input("Color (e.g., Navy Blue)")
                    size = st.selectbox("Size", ["All", "M", "L", "XL", "XXL"])
                    stock = st.number_input("Quantity", min_value=0, step=1)
                    submit_stock = st.form_submit_button("Add Stock")
                    
                    if submit_stock and color:
                        sizes_to_add = ["M", "L", "XL", "XXL"] if size == "All" else [size]
                        with conn.session as s:
                            for s_val in sizes_to_add:
                                query = text("INSERT INTO shirt_variants (design_id, color, size, stock_quantity) VALUES (:id, :c, :sz, :sq)")
                                s.execute(query, {"id": int(design_id), "c": color, "sz": s_val, "sq": stock})
                            s.commit()
                        
                        st.success(f"✅ Added {stock} {color} to inventory!")
                        time.sleep(1)
                        st.rerun()

            # Right Side: Upload Photos
            with col_right:
                st.write("**🖼️ Upload Images (Cloud Sync)**")
                with st.form("image_upload_form", clear_on_submit=True):
                    uploaded_files = st.file_uploader("Choose Images (JPG/PNG)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
                    submit_images = st.form_submit_button("Upload Photos to Cloudinary")
                    
                    if submit_images and uploaded_files:
                        with st.spinner("Uploading to cloud..."):
                            with conn.session as s:
                                for i, file in enumerate(uploaded_files):
                                    upload_result = cloudinary.uploader.upload(file)
                                    secure_url = upload_result['secure_url']
                                    
                                    is_primary = True if i == 0 else False
                                    query = text("INSERT INTO shirt_images (design_id, image_url, is_primary) VALUES (:id, :url, :ip)")
                                    s.execute(query, {"id": int(design_id), "url": secure_url, "ip": is_primary})
                                s.commit()
                            
                        st.success(f"✅ Uploaded {len(uploaded_files)} photos securely!")
                        time.sleep(1)
                        st.rerun()
                        
        else:
            st.info("No designs found. Please add a shirt in Tab 2 first!")
            
    except Exception as e:
        st.error(f"Error loading management panel: {e}")

# --- TAB 4: ORDERS & CLEANUP (NEW) ---
# --- TAB 4: ORDERS & CLEANUP (UPGRADED) ---
with tab4:
    # Section A: Actionable Pending Orders
    st.subheader("📦 Pending Orders (Needs Dispatch)")
    try:
        # Fetch ONLY Pending orders
        pending_df = conn.query("SELECT * FROM orders WHERE order_status = 'Pending' ORDER BY order_date ASC;", ttl=0)
        
        if pending_df.empty:
            st.success("🎉 All caught up! No pending orders to dispatch right now.")
        else:
            for index, row in pending_df.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 3, 1])
                    
                    with col1:
                        # Clean date formatting
                        order_time = pd.to_datetime(row['order_date']).strftime('%Y-%m-%d %I:%M %p')
                        st.write(f"**Order #{row['order_id']}**")
                        st.write(f"👤 {row['retailer_name']}")
                        st.write(f"📞 {row['retailer_phone']}")
                        st.write(f"🕒 {order_time}")
                        st.write(f"💰 ₹{row['total_value']}")
                        
                    with col2:
                        st.write("**Order Details:**")
                        # Read the JSON cart safely
                        cart_data = json.loads(row['order_summary']) if isinstance(row['order_summary'], str) else row['order_summary']
                        for v_id, item in cart_data.items():
                            st.write(f"- {item['qty']}x {item['name']} ({item['color']}, Size {item['size']})")
                            
                    with col3:
                        st.write("") # Formatting space
                        st.write("")
                        # The Action Button
                        if st.button("🚚 Dispatch Order", key=f"btn_dispatch_{row['order_id']}", use_container_width=True, type="primary"):
                            with conn.session as s:
                                # 1. Deduct the stock quantities safely
                                for v_id, item in cart_data.items():
                                    query = text("""
                                        UPDATE shirt_variants 
                                        SET stock_quantity = GREATEST(stock_quantity - :qty, 0) 
                                        WHERE variant_id = :vid
                                    """)
                                    s.execute(query, {"qty": item['qty'], "vid": int(v_id)})
                                
                                # 2. Mark order as Dispatched
                                update_order = text("UPDATE orders SET order_status = 'Dispatched' WHERE order_id = :oid")
                                s.execute(update_order, {"oid": row['order_id']})
                                
                                s.commit()
                            
                            st.success(f"✅ Order #{row['order_id']} Dispatched! Live stock updated.")
                            time.sleep(1.5)
                            st.rerun()

    except Exception as e:
        st.error(f"Could not load pending orders: {e}")

    st.markdown("---")
    
    # Section B: View Order History
    st.subheader("📥 Dispatched Order History")
    try:
        # Fetch ONLY completed orders
        history_df = conn.query("SELECT order_id, order_date, retailer_name, retailer_phone, total_value, order_summary FROM orders WHERE order_status = 'Dispatched' ORDER BY order_date DESC;", ttl=0)
        
        if history_df.empty:
            st.info("No dispatched orders yet. Dispatch a pending order to see it here!")
        else:
            history_df['order_date'] = pd.to_datetime(history_df['order_date']).dt.strftime('%Y-%m-%d %I:%M %p')
            
            # The JSON Translator
            def format_cart(cart_data):
                try:
                    cart_dict = json.loads(cart_data) if isinstance(cart_data, str) else cart_data
                    items = []
                    for key, item in cart_dict.items():
                        items.append(f"{item['qty']}x {item['name']} ({item['color']}, {item['size']})")
                    return " | ".join(items)
                except:
                    return "Error reading cart"
                    
            history_df['order_summary'] = history_df['order_summary'].apply(format_cart)
            st.dataframe(history_df, use_container_width=True, hide_index=True)
            
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
                st.warning("⚠️ Warning: This will permanently delete the design, all of its stock numbers, and instantly remove it from the Storefront.")
                
                submit_delete = st.form_submit_button("Delete Permanently", type="primary")
                
                if submit_delete:
                    del_id = del_dict[shirt_to_delete]
                    with conn.session as s:
                        s.execute(text("DELETE FROM shirt_designs WHERE design_id = :id"), {"id": int(del_id)})
                        s.commit()
                        
                    st.success(f"✅ Permanently deleted '{shirt_to_delete}'.")
                    time.sleep(1.5)
                    st.rerun()
    except Exception as e:
        st.error(f"Error loading deletion panel: {e}")
