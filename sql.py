from dotenv import load_dotenv
load_dotenv() ## load all the environemnt variables

import streamlit as st
import os
import sqlite3
import json

import google.generativeai as genai
from schema_introspector import SchemaIntrospector

## Configure Genai Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

## Helper function to get available models
def get_available_models():
    """Get list of available Gemini models that support generateContent"""
    try:
        models = genai.list_models()
        available = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                # Extract model identifier (e.g., 'gemini-1.5-pro' from 'models/gemini-1.5-pro')
                model_name = model.name
                if '/' in model_name:
                    model_id = model_name.split('/')[-1]
                else:
                    model_id = model_name
                available.append(model_id)
        return available
    except Exception as e:
        print(f"Error listing models: {e}")
        return []

## Function To Load Google Gemini Model and provide queries as response

def get_gemini_response(question, prompt):
    """Get response from Gemini with automatic model detection"""
    # First, try to get available models
    available_models = get_available_models()
    
    # List of models to try in order of preference
    # Note: Model names should be without "models/" prefix
    model_priority = [
        'gemini-1.5-pro',
        'gemini-1.5-flash',
        'gemini-1.5-pro-latest',
        'gemini-1.5-flash-latest',
        'gemini-pro',
        'gemini-1.0-pro',
        'gemini-1.0-pro-latest',
        'gemini-pro-vision'
    ]
    
    # If we found available models, use those first
    if available_models:
        # Prioritize models that are both in our list and available
        models_to_try = []
        for preferred in model_priority:
            if preferred in available_models:
                models_to_try.append(preferred)
        # Add any other available models we didn't know about
        for model in available_models:
            if model not in models_to_try:
                models_to_try.append(model)
    else:
        # Fallback to our priority list if we can't list models
        models_to_try = model_priority
    
    # Try each model in order
    last_error = None
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([prompt[0], question])
            if response and response.text:
                print(f"✅ Successfully used model: {model_name}")
                return response.text
        except Exception as e:
            last_error = e
            print(f"⚠️  Model {model_name} failed: {str(e)[:100]}")
            continue
    
    # If all models failed, raise the last error
    error_msg = f"All models failed. Last error: {last_error}"
    if available_models:
        error_msg += f"\nAvailable models: {', '.join(available_models)}"
    raise Exception(error_msg)

## Function To retrieve query from the database
def read_sql_query(sql, db_type: str, **connection_params):
    """Execute SQL query and return results with column names"""
    try:
        # Clean SQL query - remove markdown code blocks if present
        sql = sql.strip()
        if sql.startswith('```'):
            # Remove markdown code blocks
            lines = sql.split('\n')
            sql = '\n'.join([line for line in lines if not line.strip().startswith('```')])
        if sql.lower().startswith('sql'):
            # Remove 'sql' prefix if present
            sql = sql[3:].strip()
        
        # Connect based on database type
        if db_type.lower() == 'sqlite':
            conn = sqlite3.connect(connection_params.get('db_path', 'student.db'))
            cur = conn.cursor()
            cur.execute(sql)
            columns = [description[0] for description in cur.description] if cur.description else []
            rows = cur.fetchall()
            conn.commit()
            conn.close()
        elif db_type.lower() == 'postgresql':
            if not POSTGRES_AVAILABLE:
                raise ImportError("psycopg2 not installed. Install with: pip install psycopg2-binary")
            import psycopg2
            conn = psycopg2.connect(
                host=connection_params['host'],
                port=connection_params['port'],
                database=connection_params['database'],
                user=connection_params['user'],
                password=connection_params['password']
            )
            cur = conn.cursor()
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            conn.commit()
            conn.close()
        elif db_type.lower() == 'mysql':
            if not MYSQL_AVAILABLE:
                raise ImportError("pymysql not installed. Install with: pip install pymysql")
            import pymysql
            conn = pymysql.connect(
                host=connection_params['host'],
                port=connection_params['port'],
                database=connection_params['database'],
                user=connection_params['user'],
                password=connection_params['password']
            )
            cur = conn.cursor()
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()
            conn.commit()
            conn.close()
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        # Print results with column names for console
        if columns:
            print(f"Columns: {', '.join(columns)}")
        for row in rows:
            print(row)
        
        # Return both columns and rows
        return {'columns': columns, 'rows': rows}
    except Exception as e:
        st.error(f"SQL Error: {e}")
        st.error(f"Query: {sql}")
        return {'columns': [], 'rows': []}

## Function to generate dynamic prompt from schema
def generate_prompt_from_schema(schema_info: str, db_type: str, max_tables: int = None) -> str:
    """
    Generate a dynamic prompt from introspected database schema
    
    Args:
        schema_info: Formatted schema string from introspector
        db_type: Database type (sqlite, postgresql, mysql)
        max_tables: Maximum tables to include in prompt (None for all)
    
    Returns:
        Complete prompt string for the LLM
    """
    db_syntax_map = {
        'sqlite': 'SQLite',
        'postgresql': 'PostgreSQL',
        'mysql': 'MySQL'
    }
    db_syntax = db_syntax_map.get(db_type.lower(), 'SQL')
    
    prompt = f"""You are an expert in converting English questions to SQL query!

{schema_info}

**Important Rules:**
- Use proper JOINs when querying across multiple tables
- Pay attention to foreign key relationships shown above
- Use table aliases for clarity in complex queries
- Always use appropriate WHERE clauses to filter data
- Use aggregate functions (COUNT, SUM, AVG, etc.) when needed
- For views, use them when they simplify the query

**SQL Syntax Guidelines:**
- Use {db_syntax} syntax
- Always use single quotes for string literals in WHERE clauses
- Use proper date/time formatting for {db_syntax}
- Be careful with case sensitivity (check the database type)

**Query Examples:**

Example 1: "How many records are in table X?"
SQL: SELECT COUNT(*) FROM table_x;

Example 2: "List all records from table X where column Y equals value Z"
SQL: SELECT * FROM table_x WHERE column_y = 'Z';

Example 3: "Show records from table A joined with table B"
SQL: SELECT a.*, b.* FROM table_a a JOIN table_b b ON a.foreign_key = b.primary_key;

Example 4: "Get average of column X grouped by column Y"
SQL: SELECT column_y, AVG(column_x) as avg_x FROM table_x GROUP BY column_y;

**CRITICAL OUTPUT FORMAT:** 
- The SQL code should NOT have ``` in beginning or end
- Do NOT include the word "sql" in the output
- Return ONLY the SQL query, nothing else
- Do NOT add explanations or comments
- Return the query ready to execute

"""
    return prompt

## Function to get database connection and schema
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_database_schema(db_type: str, **connection_params):
    """Get and cache database schema"""
    introspector = SchemaIntrospector(cache_ttl=3600)
    try:
        schema = introspector.introspect(db_type, **connection_params)
        return schema
    except Exception as e:
        st.error(f"Error introspecting database: {e}")
        return None

## Streamlit App

st.set_page_config(page_title="NLP to SQL - Production Ready", page_icon="🔍", layout="wide")
st.header("🔍 NLP to SQL - Auto Schema Detection")

# Initialize session state
if 'db_config' not in st.session_state:
    st.session_state.db_config = {
        'db_type': 'sqlite',
        'db_path': 'student.db',
        'host': 'localhost',
        'port': 5432,
        'database': '',
        'user': '',
        'password': ''
    }
if 'schema_loaded' not in st.session_state:
    st.session_state.schema_loaded = False
if 'schema_info' not in st.session_state:
    st.session_state.schema_info = None
if 'generated_sql' not in st.session_state:
    st.session_state.generated_sql = ''
if 'edited_sql' not in st.session_state:
    st.session_state.edited_sql = ''
if 'query_executed' not in st.session_state:
    st.session_state.query_executed = False

# Sidebar with database configuration
with st.sidebar:
    st.subheader("🗄️ Database Configuration")
    
    db_type = st.selectbox(
        "Database Type",
        ['sqlite', 'postgresql', 'mysql'],
        index=0,
        help="Select your database type"
    )
    st.session_state.db_config['db_type'] = db_type
    
    if db_type == 'sqlite':
        db_path = st.text_input(
            "Database Path",
            value=st.session_state.db_config.get('db_path', 'student.db'),
            help="Path to SQLite database file"
        )
        st.session_state.db_config['db_path'] = db_path
        connection_params = {'db_path': db_path}
    else:
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("Host", value=st.session_state.db_config.get('host', 'localhost'))
            port = st.number_input("Port", value=st.session_state.db_config.get('port', 5432 if db_type == 'postgresql' else 3306))
        with col2:
            database = st.text_input("Database", value=st.session_state.db_config.get('database', ''))
        
        user = st.text_input("Username", value=st.session_state.db_config.get('user', ''))
        password = st.text_input("Password", type="password", value=st.session_state.db_config.get('password', ''))
        
        st.session_state.db_config.update({
            'host': host,
            'port': int(port),
            'database': database,
            'user': user,
            'password': password
        })
        connection_params = {
            'host': host,
            'port': int(port),
            'database': database,
            'user': user,
            'password': password
        }
    
    if st.button("🔍 Load Schema", type="primary"):
        with st.spinner("Introspecting database schema..."):
            try:
                schema = get_database_schema(db_type, **connection_params)
                if schema:
                    st.session_state.schema_info = schema
                    st.session_state.schema_loaded = True
                    st.success(f"✅ Schema loaded: {len(schema.tables)} tables, {len(schema.views)} views")
                else:
                    st.error("Failed to load schema")
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.divider()
    
    # Schema info
    if st.session_state.schema_loaded and st.session_state.schema_info:
        schema = st.session_state.schema_info
        st.subheader("📊 Schema Information")
        st.write(f"**Database:** {schema.database_name}")
        st.write(f"**Type:** {schema.database_type}")
        st.write(f"**Tables:** {len(schema.tables)}")
        st.write(f"**Views:** {len(schema.views)}")
        st.write(f"**Relationships:** {len(schema.relationships)}")
        
        with st.expander("View Tables"):
            for table in schema.tables[:20]:  # Show first 20
                st.write(f"• {table.name} ({len(table.columns)} columns)")
            if len(schema.tables) > 20:
                st.write(f"... and {len(schema.tables) - 20} more tables")
    
    st.divider()
    
    # Model information
    st.subheader("🤖 Model Information")
    try:
        available_models = get_available_models()
        if available_models:
            st.success(f"✅ {len(available_models)} model(s) available")
            for model in available_models[:3]:  # Show first 3
                st.write(f"  • {model}")
        else:
            st.warning("⚠️ Could not detect models")
    except Exception as e:
        st.error(f"Error: {e}")
    
    st.divider()
    st.subheader("💡 Tips")
    st.write("""
    - Configure database connection first
    - Click "Load Schema" to introspect
    - Ask questions in natural language
    - Works with 300+ tables automatically!
    """)

# Main content area
if not st.session_state.schema_loaded:
    st.info("👆 Please configure your database connection and click 'Load Schema' in the sidebar to begin.")
    st.stop()

question = st.text_input(
    "Ask a question in natural language:",
    key="input",
    placeholder="e.g., How many students are in class 10? Show all teachers teaching Computer Science..."
)

col1, col2 = st.columns([1, 1])
with col1:
    generate_btn = st.button("🚀 Generate SQL Query", type="primary", use_container_width=True)
with col2:
    if st.session_state.generated_sql:
        clear_btn = st.button("🗑️ Clear", use_container_width=True)
        if clear_btn:
            st.session_state.generated_sql = ''
            st.session_state.edited_sql = ''
            st.session_state.query_executed = False
            st.rerun()

# Generate SQL query
if generate_btn:
    if question:
        try:
            # Generate dynamic prompt from schema
            schema = st.session_state.schema_info
            introspector = SchemaIntrospector()
            
            # Determine max tables based on schema size (for large schemas, limit prompt size)
            max_tables = None
            if len(schema.tables) > 100:
                max_tables = 100  # Limit to first 100 tables for very large schemas
                st.info(f"⚠️ Large schema detected ({len(schema.tables)} tables). Using first 100 tables for prompt optimization.")
            
            schema_text = introspector.format_schema_for_prompt(schema, max_tables=max_tables)
            dynamic_prompt = generate_prompt_from_schema(schema_text, st.session_state.db_config['db_type'])
            
            # Get SQL query from Gemini using dynamic prompt
            with st.spinner("🤖 Generating SQL query..."):
                sql_query = get_gemini_response(question, [dynamic_prompt])
            
            # Store generated SQL in session state
            st.session_state.generated_sql = sql_query
            st.session_state.edited_sql = sql_query
            st.session_state.query_executed = False
            st.success("✅ SQL query generated! Review and edit below before executing.")
        except Exception as e:
            error_msg = str(e)
            st.error(f"❌ Error generating query: {error_msg}")
            st.session_state.generated_sql = ''
            st.session_state.edited_sql = ''
    else:
        st.warning("Please enter a question first.")

# Display SQL editor if query is generated
if st.session_state.generated_sql:
    st.divider()
    st.subheader("✏️ Review & Edit SQL Query")
    
    # Show original query info
    with st.expander("ℹ️ About this query", expanded=False):
        st.write("**Generated Query:**")
        st.code(st.session_state.generated_sql, language='sql')
        st.caption("💡 You can edit the query below before executing. This allows you to fix any issues or optimize the query.")
    
    # Editable SQL text area
    edited_sql = st.text_area(
        "Edit SQL Query (if needed):",
        value=st.session_state.edited_sql,
        height=200,
        help="You can modify the generated SQL query here before executing it. This is useful for fixing errors or optimizing queries.",
        key="sql_editor"
    )
    
    # Update session state with edited SQL
    st.session_state.edited_sql = edited_sql
    
    # Show if query was modified
    if edited_sql.strip() != st.session_state.generated_sql.strip():
        st.info("⚠️ Query has been modified from the original generated version.")
    
    # Execute button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        execute_btn = st.button("▶️ Execute Query", type="primary", use_container_width=True)
    with col2:
        copy_btn = st.button("📋 Copy SQL", use_container_width=True)
        if copy_btn:
            st.code(edited_sql, language='sql')
            st.success("SQL copied! (Use Ctrl+C to copy from the code block above)")
    
    # Execute the query
    if execute_btn:
        if edited_sql.strip():
            try:
                # Prepare connection parameters
                db_type = st.session_state.db_config['db_type']
                if db_type == 'sqlite':
                    conn_params = {'db_path': st.session_state.db_config['db_path']}
                else:
                    conn_params = {
                        'host': st.session_state.db_config['host'],
                        'port': st.session_state.db_config['port'],
                        'database': st.session_state.db_config['database'],
                        'user': st.session_state.db_config['user'],
                        'password': st.session_state.db_config['password']
                    }
                
                # Execute query and get results
                with st.spinner("🔍 Executing query..."):
                    query_result = read_sql_query(edited_sql, db_type, **conn_params)
                
                st.session_state.query_executed = True
                columns = query_result.get('columns', [])
                rows = query_result.get('rows', [])
            
                if rows:
                    st.subheader("✅ Query Results:")
                    
                    # Show executed query
                    with st.expander("📝 Executed Query", expanded=False):
                        st.code(edited_sql, language='sql')
                    
                    # Display column names
                    if columns:
                        st.write(f"**Columns:** `{', '.join(columns)}`")
                        st.write(f"**Rows returned:** {len(rows)}")
                        st.divider()
                    
                    # Display results in a more readable format
                    if len(rows) > 0:
                        # Try to display as dataframe if possible (with column names)
                        try:
                            import pandas as pd
                            if columns:
                                df = pd.DataFrame(rows, columns=columns)
                            else:
                                # If no column names, create generic ones
                                df = pd.DataFrame(rows, columns=[f'Column_{i+1}' for i in range(len(rows[0]) if rows else 0)])
                            st.dataframe(df, use_container_width=True)
                            
                            # Also show summary stats if numeric columns exist
                            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                            if numeric_cols:
                                with st.expander("📊 Summary Statistics"):
                                    st.dataframe(df[numeric_cols].describe(), use_container_width=True)
                        except Exception as e:
                            # Fallback to table display with column names
                            if columns:
                                # Use Streamlit's table display
                                try:
                                    import pandas as pd
                                    df = pd.DataFrame(rows, columns=columns)
                                    st.table(df)
                                except:
                                    # Manual markdown table as last resort
                                    col_str = " | ".join(columns)
                                    st.markdown(f"| {col_str} |")
                                    st.markdown("|" + "|".join(["---"] * len(columns)) + "|")
                                    for row in rows:
                                        row_str = " | ".join([str(val) if val is not None else '' for val in row])
                                        st.markdown(f"| {row_str} |")
                            else:
                                # Simple numbered list if no column names
                                for i, row in enumerate(rows, 1):
                                    st.write(f"{i}. {row}")
                    else:
                        st.info("No results found.")
                else:
                    st.warning("No results returned or query failed.")
            except Exception as e:
                error_msg = str(e)
                st.error(f"❌ Query Execution Error: {error_msg}")
                
                # Show helpful troubleshooting info
                with st.expander("🔧 Troubleshooting"):
                    st.write("**Common SQL errors:**")
                    st.write("1. **Syntax errors**: Check SQL syntax matches your database type")
                    st.write("2. **Table/Column names**: Verify table and column names exist")
                    st.write("3. **Alias issues**: Check that all table aliases are properly defined")
                    st.write("4. **JOIN conditions**: Ensure JOIN conditions are correct")
                    
                    st.write("**Tips:**")
                    st.write("- Review the SQL query above and fix any issues")
                    st.write("- Edit the query in the text area and try again")
                    st.write("- Check the database schema in the sidebar")
        else:
            st.warning("Please enter a SQL query to execute.")









