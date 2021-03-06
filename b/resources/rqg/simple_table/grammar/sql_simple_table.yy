query:
 	select ;

select:
	SELECT select_from FROM BUCKET_NAME WHERE condition ORDER BY order_by |
	SELECT select_from FROM BUCKET_NAME WHERE condition GROUP BY field_list |
	SELECT select_from FROM BUCKET_NAME WHERE condition;

create_index:
	CREATE INDEX INDEX_NAME ON BUCKET_NAME(FIELD_LIST) WHERE condition |
	CREATE INDEX INDEX_NAME ON BUCKET_NAME(condition) |
	CREATE INDEX INDEX_NAME ON BUCKET_NAME(USER_FIELD_LIST);

select_from:
	* | COUNT(*) |  COUNT( DISTINCT field_list ) | SUM( NUMERIC_FIELD ) | SUM(DISTINCT NUMERIC_FIELD ) | AVG( NUMERIC_FIELD ) |  AVG( DISTINCT NUMERIC_FIELD ) | AVG( DISTINCT DATETIME_FIELD ) |  MAX( NUMERIC_FIELD ) | MAX( DATETIME_FIELD ) | MIN( NUMERIC_FIELD ) | MIN( DATETIME_FIELD );

select_from:
	* | COUNT(*) |  COUNT( DISTINCT field_list ) | SUM( NUMERIC_FIELD ) | SUM(DISTINCT NUMERIC_FIELD ) | AVG( NUMERIC_FIELD ) |  AVG( DISTINCT NUMERIC_FIELD ) | AVG( DISTINCT DATETIME_FIELD ) |  MAX( NUMERIC_FIELD ) | MAX( DATETIME_FIELD ) | MIN( NUMERIC_FIELD ) | MIN( DATETIME_FIELD );

condition:
	numeric_condition | string_condition | datetime_condition| (condition) AND (condition) | (condition) OR (condition);

order_by:
	field_list;

# NUMERIC RULES

numeric_condition:
	numeric_field < numeric_value |
	numeric_field = numeric_value |
	numeric_field > numeric_value |
	numeric_field  >= numeric_value |
	numeric_field  <= numeric_value |
	(numeric_condition) AND (numeric_condition)|
	(numeric_condition) OR (numeric_condition)|
	NOT (numeric_condition) |
	numeric_between_condition |
	numeric_is_not_null |
	numeric_not_equals_condition |
	numeric_is_null |
	numeric_in_conidtion ;

numeric_equals_condition:
	numeric_field EQUALS numeric_value | numeric_field = numeric_value | numeric_field == numeric_value ;

numeric_not_equals_condition:
	numeric_field NOT EQUALS numeric_value | numeric_field != numeric_value ;

numeric_in_conidtion:
	numeric_field IN [ numeric_field_list ];

numeric_between_condition:
	NUMERIC_FIELD BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

numeric_not_between_condition:
	NUMERIC_FIELD NOT BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

numeric_is_not_null:
	NUMERIC_FIELD IS NOT NULL;

numeric_is_missing:
	NUMERIC_FIELD IS MISSING;

numeric_is_not_missing:
	NUMERIC_FIELD IS NOT MISSING;

numeric_is_valued:
	NUMERIC_FIELD IS VALUED;

numeric_is_not_valued:
	NUMERIC_FIELD IS NOT VALUED;

numeric_is_null:
	NUMERIC_FIELD IS NULL;

numeric_field_list:
	LIST;

numeric_field:
	NUMERIC_FIELD;

numeric_value:
	NUMERIC_VALUE;

# DATE TIME RULES

datetime_condition:
	datetime_field < DATETIME_VALUES |
	datetime_field = DATETIME_VALUES |
	datetime_field > DATETIME_VALUES |
	datetime_field  >= DATETIME_VALUES |
	datetime_field  <= DATETIME_VALUES |
	(datetime_condition) AND (datetime_condition)|
	(datetime_condition) OR (datetime_condition)|
	NOT (datetime_condition) |
	datetime_between_condition |
	datetime_is_not_null |
	datetime_not_equals_condition |
	datetime_is_null |
	datetime_in_conidtion ;

datetime_equals_condition:
	datetime_field EQUALS DATETIME_VALUES | datetime_field = DATETIME_VALUES | datetime_field == DATETIME_VALUES ;

datetime_not_equals_condition:
	datetime_equals_condition NOT EQUALS DATETIME_VALUES | datetime_field != DATETIME_VALUES ;

datetime_in_conidtion:
	datetime_field IN [ datetime_field_list ];

datetime_between_condition:
	DATETIME_FIELD BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

datetime_not_between_condition:
	DATETIME_FIELD NOT BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

datetime_is_not_null:
	DATETIME_FIELD IS NOT NULL;

datetime_is_missing:
	DATETIME_FIELD IS MISSING;

datetime_is_not_missing:
	DATETIME_FIELD IS NOT MISSING;

datetime_is_valued:
	DATETIME_FIELD IS VALUED;

datetime_is_not_valued:
	DATETIME_FIELD IS NOT VALUED;

datetime_is_null:
	DATETIME_FIELD IS NULL;

datetime_field_list:
	LIST;

is_not_missing:
	IS NOT MISSING;

datetime_field:
	DATETIME_FIELD;

# STRING RULES

string_condition:
	string_field < string_values |
	string_field > string_values |
	string_field  >= string_values |
	string_field  <= string_values |
	(string_condition) AND (string_condition) |
	(string_condition) OR (string_condition) |
	string_not_between_condition |
	NOT (string_condition) |
	string_is_not_null |
	string_is_null |
	string_not_equals_condition |
	string_in_conidtion |
	string_like_condition |
	string_equals_condition |
	string_not_like_condition ;

string_equals_condition:
	string_field EQUALS string_values | string_field = string_values | string_field == string_values;

string_not_equals_condition:
	string_field != string_values | string_field <> string_values ;

string_between_condition:
	string_field BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

string_not_between_condition:
	string_field NOT BETWEEN LOWER_BOUND_VALUE and UPPER_BOUND_VALUE;

string_is_not_null:
	string_field IS NOT NULL;

string_in_conidtion:
	string_field IN [ string_field_list ];

string_is_null:
	string_field IS NULL;

string_like_condition:
	string_field LIKE 'STRING_VALUES%' | string_field LIKE '%STRING_VALUES' | string_field LIKE STRING_VALUES | string_field LIKE '%STRING_VALUES%';

string_not_like_condition:
	string_field NOT LIKE 'STRING_VALUES%' | string_field NOT LIKE '%STRING_VALUES' | string_field NOT LIKE STRING_VALUES |  string_field NOT LIKE '%STRING_VALUES%';

string_field_list:
	LIST;

string_is_missing:
	STRING_FIELD IS MISSING;

string_is_not_missing:
	STRING_FIELD IS NOT MISSING;

string_is_valued:
	STRING_FIELD IS VALUED;

string_is_not_valued:
	STRING_FIELD IS NOT VALUED;

string_field:
	STRING_FIELD;

string_values:
	STRING_VALUES;

# BOOLEAN RULES

bool_condition:
	bool_equals_condition | bool_not_equals_condition;

bool_equals_condition:
	bool_field EQUALS bool_value | bool_field = bool_value | bool_field == bool_value ;

bool_not_equals_condition:
	bool_field NOT EQUALS bool_value | bool_field != bool_value ;

bool_field:
	BOOL_FIELD;

bool_value:
	true | false;

field_list:
	NUMERIC_FIELD_LIST | STRING_FIELD_LIST | DATETIME_FIELD_LIST | NUMERIC_FIELD_LIST, STRING_FIELD_LIST, DATETIME_FIELD_LIST | NUMERIC_FIELD_LIST, STRING_FIELD_LIST | STRING_FIELD_LIST, DATETIME_FIELD_LIST;
