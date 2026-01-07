"""
Database Schema Introspector
Automatically extracts table structures, columns, relationships, and constraints
from any database (SQLite, PostgreSQL, MySQL, etc.)
"""

import sqlite3
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import hashlib
import time

try:
    import psycopg2
    from psycopg2 import sql
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

try:
    import pymysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


@dataclass
class ColumnInfo:
    """Information about a database column"""
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    foreign_table: Optional[str] = None
    foreign_column: Optional[str] = None
    default_value: Optional[str] = None
    is_unique: bool = False


@dataclass
class TableInfo:
    """Information about a database table"""
    name: str
    columns: List[ColumnInfo]
    table_type: str = "TABLE"  # TABLE, VIEW, etc.


@dataclass
class SchemaInfo:
    """Complete database schema information"""
    database_name: str
    database_type: str
    tables: List[TableInfo]
    views: List[TableInfo]
    relationships: List[Dict]  # Foreign key relationships
    extracted_at: str


class SchemaIntrospector:
    """Introspects database schema for multiple database types"""
    
    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize schema introspector
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        self.cache_ttl = cache_ttl
        self._schema_cache: Dict[str, Tuple[SchemaInfo, float]] = {}
    
    def _get_cache_key(self, db_type: str, connection_params: Dict) -> str:
        """Generate cache key from connection parameters"""
        key_str = f"{db_type}:{json.dumps(connection_params, sort_keys=True)}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached_schema(self, cache_key: str) -> Optional[SchemaInfo]:
        """Get cached schema if still valid"""
        if cache_key in self._schema_cache:
            schema, timestamp = self._schema_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return schema
            else:
                del self._schema_cache[cache_key]
        return None
    
    def _cache_schema(self, cache_key: str, schema: SchemaInfo):
        """Cache schema with timestamp"""
        self._schema_cache[cache_key] = (schema, time.time())
    
    def introspect_sqlite(self, db_path: str) -> SchemaInfo:
        """Introspect SQLite database"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        tables = []
        views = []
        relationships = []
        
        try:
            # Get all tables and views
            cursor = conn.cursor()
            
            # Get tables
            cursor.execute("""
                SELECT name, type 
                FROM sqlite_master 
                WHERE type IN ('table', 'view')
                AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            
            for row in cursor.fetchall():
                table_name = row['name']
                table_type = row['type']
                
                # Get column information
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = []
                
                for col_row in cursor.fetchall():
                    col_info = ColumnInfo(
                        name=col_row[1],
                        data_type=col_row[2],
                        is_nullable=not col_row[3],
                        is_primary_key=bool(col_row[5]),
                        is_foreign_key=False,  # Will be updated below
                        default_value=col_row[4]
                    )
                    columns.append(col_info)
                
                # Get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                for fk_row in cursor.fetchall():
                    # fk_row: (id, seq, table, from, to, on_update, on_delete, match)
                    fk_from = fk_row[3]
                    fk_table = fk_row[2]
                    fk_to = fk_row[4]
                    
                    # Update column info
                    for col in columns:
                        if col.name == fk_from:
                            col.is_foreign_key = True
                            col.foreign_table = fk_table
                            col.foreign_column = fk_to
                    
                    relationships.append({
                        'from_table': table_name,
                        'from_column': fk_from,
                        'to_table': fk_table,
                        'to_column': fk_to
                    })
                
                # Get indexes to check for unique constraints
                cursor.execute(f"PRAGMA index_list({table_name})")
                for idx_row in cursor.fetchall():
                    idx_name = idx_row[1]
                    is_unique = bool(idx_row[2])
                    if is_unique:
                        cursor.execute(f"PRAGMA index_info({idx_name})")
                        for idx_info in cursor.fetchall():
                            col_name = idx_info[2]
                            for col in columns:
                                if col.name == col_name:
                                    col.is_unique = True
                
                table_info = TableInfo(
                    name=table_name,
                    columns=columns,
                    table_type=table_type.upper()
                )
                
                if table_type == 'view':
                    views.append(table_info)
                else:
                    tables.append(table_info)
            
            schema = SchemaInfo(
                database_name=db_path,
                database_type="SQLite",
                tables=tables,
                views=views,
                relationships=relationships,
                extracted_at=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            return schema
            
        finally:
            conn.close()
    
    def introspect_postgresql(self, host: str, port: int, database: str, 
                             user: str, password: str, schema: str = 'public') -> SchemaInfo:
        """Introspect PostgreSQL database"""
        if not POSTGRES_AVAILABLE:
            raise ImportError("psycopg2 not installed. Install with: pip install psycopg2-binary")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        tables = []
        views = []
        relationships = []
        
        try:
            cursor = conn.cursor()
            
            # Get all tables and views
            cursor.execute("""
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_name
            """, (schema,))
            
            for row in cursor.fetchall():
                table_name = row[0]
                table_type = row[1]
                
                # Get column information
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                """, (schema, table_name))
                
                columns = []
                for col_row in cursor.fetchall():
                    col_info = ColumnInfo(
                        name=col_row[0],
                        data_type=col_row[1],
                        is_nullable=col_row[2] == 'YES',
                        is_primary_key=False,  # Will be updated below
                        is_foreign_key=False,  # Will be updated below
                        default_value=col_row[3]
                    )
                    columns.append(col_info)
                
                # Get primary keys
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'PRIMARY KEY'
                """, (schema, table_name))
                
                pk_columns = [row[0] for row in cursor.fetchall()]
                for col in columns:
                    if col.name in pk_columns:
                        col.is_primary_key = True
                
                # Get foreign keys
                cursor.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = %s
                    AND tc.table_name = %s
                """, (schema, table_name))
                
                for fk_row in cursor.fetchall():
                    col_name, fk_table, fk_column = fk_row
                    for col in columns:
                        if col.name == col_name:
                            col.is_foreign_key = True
                            col.foreign_table = fk_table
                            col.foreign_column = fk_column
                    
                    relationships.append({
                        'from_table': table_name,
                        'from_column': col_name,
                        'to_table': fk_table,
                        'to_column': fk_column
                    })
                
                # Get unique constraints
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    WHERE tc.table_schema = %s
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'UNIQUE'
                """, (schema, table_name))
                
                unique_columns = [row[0] for row in cursor.fetchall()]
                for col in columns:
                    if col.name in unique_columns:
                        col.is_unique = True
                
                table_info = TableInfo(
                    name=table_name,
                    columns=columns,
                    table_type=table_type
                )
                
                if table_type == 'VIEW':
                    views.append(table_info)
                else:
                    tables.append(table_info)
            
            schema = SchemaInfo(
                database_name=database,
                database_type="PostgreSQL",
                tables=tables,
                views=views,
                relationships=relationships,
                extracted_at=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            return schema
            
        finally:
            conn.close()
    
    def introspect_mysql(self, host: str, port: int, database: str,
                        user: str, password: str) -> SchemaInfo:
        """Introspect MySQL database"""
        if not MYSQL_AVAILABLE:
            raise ImportError("pymysql not installed. Install with: pip install pymysql")
        
        conn = pymysql.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        tables = []
        views = []
        relationships = []
        
        try:
            cursor = conn.cursor()
            
            # Get all tables and views
            cursor.execute("""
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_name
            """, (database,))
            
            for row in cursor.fetchall():
                table_name = row[0]
                table_type = row[1]
                
                # Get column information
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        column_key,
                        extra
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                """, (database, table_name))
                
                columns = []
                for col_row in cursor.fetchall():
                    col_info = ColumnInfo(
                        name=col_row[0],
                        data_type=col_row[1],
                        is_nullable=col_row[2] == 'YES',
                        is_primary_key=col_row[4] == 'PRI',
                        is_foreign_key=False,  # Will be updated below
                        default_value=str(col_row[3]) if col_row[3] else None
                    )
                    columns.append(col_info)
                
                # Get foreign keys
                cursor.execute("""
                    SELECT
                        column_name,
                        referenced_table_name,
                        referenced_column_name
                    FROM information_schema.key_column_usage
                    WHERE table_schema = %s
                    AND table_name = %s
                    AND referenced_table_name IS NOT NULL
                """, (database, table_name))
                
                for fk_row in cursor.fetchall():
                    col_name, fk_table, fk_column = fk_row
                    for col in columns:
                        if col.name == col_name:
                            col.is_foreign_key = True
                            col.foreign_table = fk_table
                            col.foreign_column = fk_column
                    
                    relationships.append({
                        'from_table': table_name,
                        'from_column': col_name,
                        'to_table': fk_table,
                        'to_column': fk_column
                    })
                
                table_info = TableInfo(
                    name=table_name,
                    columns=columns,
                    table_type=table_type
                )
                
                if table_type == 'VIEW':
                    views.append(table_info)
                else:
                    tables.append(table_info)
            
            schema = SchemaInfo(
                database_name=database,
                database_type="MySQL",
                tables=tables,
                views=views,
                relationships=relationships,
                extracted_at=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            
            return schema
            
        finally:
            conn.close()
    
    def introspect(self, db_type: str, **connection_params) -> SchemaInfo:
        """
        Introspect database schema with caching
        
        Args:
            db_type: 'sqlite', 'postgresql', or 'mysql'
            **connection_params: Connection parameters specific to database type
        
        Returns:
            SchemaInfo object with complete schema information
        """
        cache_key = self._get_cache_key(db_type, connection_params)
        
        # Check cache first
        cached_schema = self._get_cached_schema(cache_key)
        if cached_schema:
            return cached_schema
        
        # Introspect based on database type
        db_type_lower = db_type.lower()
        
        if db_type_lower == 'sqlite':
            if 'db_path' not in connection_params:
                raise ValueError("SQLite requires 'db_path' parameter")
            schema = self.introspect_sqlite(connection_params['db_path'])
        elif db_type_lower == 'postgresql':
            required = ['host', 'port', 'database', 'user', 'password']
            missing = [p for p in required if p not in connection_params]
            if missing:
                raise ValueError(f"PostgreSQL requires parameters: {', '.join(missing)}")
            schema = self.introspect_postgresql(**connection_params)
        elif db_type_lower == 'mysql':
            required = ['host', 'port', 'database', 'user', 'password']
            missing = [p for p in required if p not in connection_params]
            if missing:
                raise ValueError(f"MySQL requires parameters: {', '.join(missing)}")
            schema = self.introspect_mysql(**connection_params)
        else:
            raise ValueError(f"Unsupported database type: {db_type}. Supported: sqlite, postgresql, mysql")
        
        # Cache the schema
        self._cache_schema(cache_key, schema)
        
        return schema
    
    def format_schema_for_prompt(self, schema: SchemaInfo, max_tables: Optional[int] = None) -> str:
        """
        Format schema information as a prompt-friendly string
        
        Args:
            schema: SchemaInfo object
            max_tables: Maximum number of tables to include (None for all)
        
        Returns:
            Formatted string describing the database schema
        """
        lines = []
        lines.append(f"Database: {schema.database_name} ({schema.database_type})")
        lines.append(f"Schema extracted at: {schema.extracted_at}")
        lines.append("")
        
        # Tables
        tables_to_include = schema.tables[:max_tables] if max_tables else schema.tables
        lines.append(f"**TABLES ({len(tables_to_include)} of {len(schema.tables)}):**")
        lines.append("")
        
        for table in tables_to_include:
            lines.append(f"### Table: `{table.name}`")
            lines.append("Columns:")
            for col in table.columns:
                col_desc = f"  - `{col.name}` ({col.data_type})"
                if col.is_primary_key:
                    col_desc += " [PRIMARY KEY]"
                if col.is_foreign_key:
                    col_desc += f" [FOREIGN KEY -> {col.foreign_table}.{col.foreign_column}]"
                if col.is_unique and not col.is_primary_key:
                    col_desc += " [UNIQUE]"
                if not col.is_nullable:
                    col_desc += " [NOT NULL]"
                if col.default_value:
                    col_desc += f" [DEFAULT: {col.default_value}]"
                lines.append(col_desc)
            lines.append("")
        
        # Views
        if schema.views:
            lines.append(f"**VIEWS ({len(schema.views)}):**")
            lines.append("")
            for view in schema.views:
                lines.append(f"### View: `{view.name}`")
                lines.append("Columns:")
                for col in view.columns:
                    lines.append(f"  - `{col.name}` ({col.data_type})")
                lines.append("")
        
        # Relationships summary
        if schema.relationships:
            lines.append("**KEY RELATIONSHIPS:**")
            for rel in schema.relationships[:20]:  # Limit to first 20
                lines.append(f"  - `{rel['from_table']}.{rel['from_column']}` -> `{rel['to_table']}.{rel['to_column']}`")
            if len(schema.relationships) > 20:
                lines.append(f"  ... and {len(schema.relationships) - 20} more relationships")
            lines.append("")
        
        if max_tables and len(schema.tables) > max_tables:
            lines.append(f"*Note: Showing first {max_tables} of {len(schema.tables)} tables. Use JOINs to query across tables.*")
        
        return "\n".join(lines)




