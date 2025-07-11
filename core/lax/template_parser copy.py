import re
from typing import Any, Dict, List, Union
# """
# 模板引擎使用示例

# 基础用法:
# 1. 简单变量替换: {{variable}}
# 2. 条件判断: {% if condition %}...{% endif %}
# 3. 循环结构: {% for item in items %}...{% endfor %}
# """
class TemplateParser:
    """A lightweight template engine supporting variables, conditions and loops."""
    
    def __init__(self, template: str):
        """Initialize the template parser with a template string."""
        self.template = template
        self.compiled = None
        self.custom_functions = {}
        
    def register_function(self, name: str, func: callable) -> None:
        """
        Register a custom function to be available in template expressions.
        
        Args:
            name: The name to use in templates
            func: The function to register
        """
        self.custom_functions[name] = func
        
    def register_functions(self, functions: Dict[str, callable]) -> None:
        """
        Register multiple custom functions at once.
        
        Args:
            functions: Dictionary of function names to functions
        """
        self.custom_functions.update(functions)

    def compile_template(self) -> None:
        """Compile the template into an intermediate representation."""
        # Split template into static parts and control blocks
        pattern = re.compile(
            r'(\{\%.*?\%\})|'  # control blocks {% ... %}
            r'(\{\{.*?\}\})'    # variables {{ ... }}
        )
        self.compiled = pattern.split(self.template)
        
    def render(self, context: Dict[str, Any]) -> str:
        """
        Render the template with the given context.
        
        Args:
            context: A dictionary containing variables for template rendering
            
        Returns:
            The rendered template as a string
        """
        # Security check: validate context keys
        for key in context.keys():
            if not isinstance(key, str) or not key.isidentifier():
                raise ValueError(f"Invalid context key: {key}. Keys must be valid Python identifiers")
        
        if self.compiled is None:
            print("Compiling template...")
            self.compile_template()
            
        output = []
        i = 0
        while i < len(self.compiled):
            part = self.compiled[i]
            
            if part is None:
                i += 1
                continue
                
            # Handle variables {{ var }} and nested {{ var.attr }} and eval expressions
            if part.startswith('{{') and part.endswith('}}'):
                # print(f"\nProcessing variable part: {part}")
                var_expr = part[2:-2].strip()
                # print(f"Extracted expression: {var_expr}")
                
                # Check if this is an eval expression (starts with =)
                if var_expr.startswith('='):
                    try:
                        # Evaluate the expression (after =)
                        expr = var_expr[1:]
                        if not self._is_safe_expression(expr):
                            raise ValueError("Potentially dangerous expression detected")
                            
                        # Create safe evaluation environment
                        safe_globals = self._get_safe_globals()
                        eval_globals = {**safe_globals, **self.custom_functions}
                        
                        result = eval(expr, eval_globals, context)
                        output.append(str(result))
                    except Exception as e:
                        output.append(f'[Error: {str(e)}]')
                elif '.' in var_expr:
                    # print(f"DEBUG - Processing nested variable: {var_expr}")  # Debug
                    # Handle nested attribute access
                    parts = var_expr.split('.')
                    current = context.get(parts[0], {})
                    for part_name in parts[1:]:
                        if isinstance(current, dict):
                            current = current.get(part_name, '')
                        else:
                            current = getattr(current, part_name, '')
                        if current is None:
                            current = ''
                            break
                    output.append(str(current))
                else:
                    # Simple variable access
                    output.append(str(context.get(var_expr, '')))
                i += 1
                
            # Handle control blocks {% ... %}
            elif part.startswith('{%') and part.endswith('%}'):
                block = part[2:-2].strip()
                
                # Handle if condition
                if block.startswith('if '):
                    condition = block[3:].strip()
                    result, updated_context = self._evaluate_condition(condition, context)
                    # Merge all variables except special ones and functions
                    for k, v in updated_context.items():
                        if not k.startswith('__') and k not in self.custom_functions:
                            # Only update context if the key doesn't exist or was modified
                            if k not in context or context[k] != v:
                                context[k] = v
                    # Ensure final_price is available in context if it was calculated
                    if 'final_price' in updated_context:
                        context['final_price'] = updated_context['final_price']
                    
                    # Find matching endif using helper method
                    endif_idx = self._skip_control_block(i, 'if', 'endif')
                    if endif_idx == len(self.compiled):
                        i += 1
                        continue
                    
                    # Find else if exists
                    else_idx = -1
                    for j in range(i+1, endif_idx):
                        part = self.compiled[j]
                        if isinstance(part, str) and part.strip() in ('{% else %}', 'else'):
                            else_idx = j
                            break
                    
                    # print(f"DEBUG - Control block boundaries: else={else_idx}, endif={endif_idx}")
                    
                    # Process the appropriate block
                    if result:
                        # Process if block (from current position to else or endif)
                        end_idx = else_idx if else_idx != -1 else endif_idx
                        if_content = self.compiled[i+1:end_idx]
                        # print(f"DEBUG - Processing if block from {i+1} to {end_idx}")
                        
                        if_parser = TemplateParser('')
                        if_parser.compiled = if_content
                        rendered = if_parser.render(context)
                        output.append(rendered)
                    elif else_idx != -1:
                        # Process else block
                        else_content = self.compiled[else_idx+1:endif_idx]
                        # print(f"DEBUG - Processing else block from {else_idx+1} to {endif_idx}")
                        
                        else_parser = TemplateParser('')
                        else_parser.compiled = else_content
                        rendered = else_parser.render(context)
                        output.append(rendered)
                    
                    # Skip to after endif
                    i = endif_idx + 1
                    
                # Handle for loop
                elif block.startswith('for ') and ' in ' in block:
                    loop_var, iterable = self._parse_for_block(block)
                    items = self._get_iterable(iterable, context)
                    
                    # Collect loop content
                    loop_content = []
                    j = i + 1
                    while j < len(self.compiled):
                        inner_part = self.compiled[j]
                        if (isinstance(inner_part, str) and 
                            inner_part.startswith('{% endfor %}')):
                            break
                        loop_content.append(str(inner_part) if inner_part else '')
                        j += 1
                        
                    # Render loop
                    # print(f"DEBUG - For loop items: {items}")  # Debug
                    loop_output = []
                    total_items = len(items)
                    for item_idx, item in enumerate(items):
                        loop_context = context.copy()
                        loop_context[loop_var] = item
                        
                        # Add loop variable with iteration info
                        loop_context['loop'] = {
                            'index': item_idx + 1,
                            'index0': item_idx,
                            'first': item_idx == 0,
                            'last': item_idx == total_items - 1,
                            'length': total_items
                        }
                        
                        # Render loop content with current item
                        item_output = []
                        j = 0
                        while j < len(loop_content):
                            part = loop_content[j]
                            if part is None:
                                j += 1
                                continue
                            
                            # Handle if conditions inside for loop
                            if (isinstance(part, str) and 
                                part.startswith('{% if ') and 
                                part.endswith('%}')):
                                condition = part[6:-2].strip()
                                result, _ = self._evaluate_condition(condition, loop_context)
                                
                                # Find matching endif
                                endif_idx = j + 1
                                nested_depth = 1
                                while endif_idx < len(loop_content):
                                    inner_part = loop_content[endif_idx]
                                    if (isinstance(inner_part, str) and 
                                        inner_part.startswith('{% if ') and 
                                        inner_part.endswith('%}')):
                                        nested_depth += 1
                                    elif (isinstance(inner_part, str) and 
                                          inner_part.startswith('{% endif %}')):
                                        nested_depth -= 1
                                        if nested_depth == 0:
                                            break
                                    endif_idx += 1
                                
                                # Process if block if condition is true
                                if result:
                                    if_content = loop_content[j+1:endif_idx]
                                    rendered = self._render_parts(if_content, loop_context)
                                    item_output.append(rendered)
                                
                                # Skip to after endif
                                j = endif_idx + 1
                            
                            # Handle variable references
                            elif isinstance(part, str) and part.startswith('{{') and part.endswith('}}'):
                                var_expr = part[2:-2].strip()
                                # print(f"DEBUG - Evaluating variable: {var_expr}")  # Debug
                            
                                if var_expr.startswith('='):
                                    # Handle eval expressions
                                    try:
                                        expr = var_expr[1:]
                                        if not self._is_safe_expression(expr):
                                            raise ValueError("Potentially dangerous expression detected")
                                        
                                        safe_globals = self._get_safe_globals()
                                        eval_globals = {**safe_globals, **self.custom_functions}
                                    
                                        result = eval(expr, eval_globals, loop_context)
                                        value = str(result)
                                    except Exception as e:
                                        value = f'[Error: {str(e)}]'
                                elif '.' in var_expr:
                                    # Handle nested attributes
                                    parts = var_expr.split('.')
                                    current = loop_context.get(parts[0], {})
                                    for part_name in parts[1:]:
                                        if isinstance(current, dict):
                                            current = current.get(part_name, '')
                                        else:
                                            current = getattr(current, part_name, '')
                                        if current is None:
                                            current = ''
                                            break
                                    value = str(current)
                                else:
                                    # Handle simple variable
                                    value = str(loop_context.get(var_expr, ''))
                            
                                # print(f"DEBUG - Variable value: {value}")  # Debug
                                item_output.append(value)
                                j += 1
                            
                            else:
                                # Handle literal text (preserve whitespace and newlines)
                                item_output.append(str(part))
                                j += 1
                        
                        rendered_item = ''.join(item_output)
                        # print(f"DEBUG - Rendered item {item_idx}:\n{repr(rendered_item)}")  # Debug
                        loop_output.append(rendered_item)
                    
                    if loop_output:
                        # Join all loop items with newlines and add to output
                        loop_result = '\n'.join(loop_output)
                        output.append(loop_result)
                    else:
                        # print("DEBUG - No loop output generated")
                        pass
                    
                    # Skip to end of loop
                    i = j + 1
                    
                # Handle endif/endfor
                elif block in ('endif', 'endfor'):
                    i += 1
                    
                else:
                    i += 1
                    
            # Static text
            else:
                output.append(str(part) if part else '')
                i += 1
                
        # Clean up the output by removing excessive newlines
        result = ''.join(output)
        return self._clean_output(result)
    
    def _get_safe_globals(self) -> Dict[str, Any]:
        """Return a dictionary of safe builtins for eval/exec."""
        safe_builtins = {
            'None': None,
            'True': True,
            'False': False,
            'bool': bool,
            'int': int,
            'float': float,
            'str': str,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'len': len,
            'sum': sum,
            'min': min,
            'max': max,
            'abs': abs,
            'round': round
        }
        return safe_builtins

    def _is_safe_expression(self, expr: str) -> bool:
        """Check if an expression contains potentially dangerous operations."""
        forbidden = [
            'import', 'open', 'exec', 'eval', 'system', 'subprocess',
            '__import__', 'getattr', 'setattr', 'delattr', 'compile',
            'globals', 'locals', 'vars', 'dir', 'help', 'reload',
            'input', 'file', 'execfile', 'reload', 'exit', 'quit'
        ]
        expr_lower = expr.lower()
        return not any(keyword in expr_lower for keyword in forbidden)

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> tuple:
        """
        Evaluate a condition expression or code block in the given context.
        Returns (result, updated_context) where updated_context contains any new variables
        created during evaluation.
        """
        try:
            if not self._is_safe_expression(condition):
                raise ValueError(f"Potentially dangerous expression: {condition}")
                
            # Special handling for loop variables
            if 'loop.' in condition:
                # Handle not conditions
                has_not = 'not ' in condition
                loop_var = condition.split('loop.')[-1].strip()
                if has_not:
                    loop_var = loop_var.replace('not ', '').strip()
                
                loop_info = context.get('loop', {})
                result = False
                
                if loop_var == 'last':
                    result = loop_info.get('last', False)
                elif loop_var == 'first':
                    result = loop_info.get('first', False)
                elif loop_var == 'index':
                    result = bool(loop_info.get('index', 0))
                elif loop_var == 'index0':
                    result = bool(loop_info.get('index0', 0))
                
                # Invert result if 'not' was present
                return (not result if has_not else result), context
                    
            # Create safe evaluation environment
            safe_globals = self._get_safe_globals()
            eval_globals = {**safe_globals, **self.custom_functions}
            
            # Make a copy of context to avoid modifying the original
            local_vars = context.copy()
            
            # Handle multi-line code blocks
            if '\n' in condition.strip():
                # Compile and execute the code block in restricted environment
                code = compile(condition, '<string>', 'exec')
                exec(code, eval_globals, local_vars)
                # The last expression's value should be in __result__
                result = bool(local_vars.get('__result__', False))
                # Return result and updated context (excluding special vars)
                updated_context = {k: v for k, v in local_vars.items() 
                                 if not k.startswith('__') and k not in self.custom_functions}
                
                # Debug output
                print(f"DEBUG - Condition evaluation result: {result}")
                print(f"DEBUG - Local vars after execution: {local_vars.keys()}")
                print(f"DEBUG - Updated context to return: {updated_context.keys()}")
                
                # Ensure all calculated variables are included
                for k, v in local_vars.items():
                    if (not k.startswith('__') and 
                        k not in self.custom_functions and 
                        k not in updated_context):
                        updated_context[k] = v
                        print(f"DEBUG - Added {k} to context: {v}")
                
                return result, updated_context
            
            # Handle function calls with = prefix
            if condition.startswith('='):
                result = bool(eval(condition[1:], eval_globals, local_vars))
                return result, local_vars
            
            # Handle nested attribute access (e.g. user.is_admin)
            if '.' in condition:
                parts = condition.split('.')
                current = local_vars.get(parts[0], {})
                for part in parts[1:]:
                    if isinstance(current, dict):
                        current = current.get(part, None)
                    else:
                        current = getattr(current, part, None)
                    if current is None:
                        return False, local_vars
                # Handle empty collections
                if isinstance(current, (list, dict, set)) and not current:
                    return False, local_vars
                return bool(current), local_vars
            
            # Handle direct variable reference
            if condition in local_vars:
                value = local_vars[condition]
                if isinstance(value, (list, dict, set)):
                    return len(value) > 0, local_vars
                return bool(value), local_vars
                
            # Evaluate other expressions
            result = bool(eval(condition, eval_globals, local_vars))
            return result, local_vars
            
        except Exception:
            return False, context
            
    def _skip_control_block(self, start_idx: int, start_tag: str, end_tag: str) -> int:
        """Skip a control block until matching end tag is found."""
        if start_idx >= len(self.compiled):
            return len(self.compiled)
            
        depth = 1
        i = start_idx + 1
        # print(f"DEBUG - Searching for {end_tag} starting from {start_idx}")
        
        while i < len(self.compiled):
            part = self.compiled[i]
            if isinstance(part, str) and part.startswith('{%') and part.endswith('%}'):
                block = part[2:-2].strip()
                # print(f"DEBUG - Token {i}: {block} (depth={depth})")
                
                # Handle nested blocks
                if block.startswith('if ') or block.startswith('for '):
                    depth += 1
                    # print(f"DEBUG - Found nested block, depth increased to {depth}")
                elif block == end_tag:
                    depth -= 1
                    # print(f"DEBUG - Found {end_tag}, depth decreased to {depth}")
                    if depth == 0:
                        # print(f"DEBUG - Found matching {end_tag} at {i}")
                        return i
                elif block == 'else' and depth == 1:
                    # print(f"DEBUG - Found else at {i}")
                    # Don't decrease depth for else blocks
                    pass
                elif block in ['endif', 'endfor'] and depth > 1:
                    depth -= 1
                    # print(f"DEBUG - Found closing tag in nested block, depth decreased to {depth}")
            
            i += 1
        
        # print(f"DEBUG - Error: Reached end without finding matching {end_tag} (current depth: {depth})")
        # print(f"DEBUG - Last processed block: {self.compiled[i-1] if i > 0 else 'None'}")
        return len(self.compiled)

    def _clean_output(self, output: str) -> str:
        """Clean up the final output by removing excessive newlines and whitespace."""
        lines = output.split('\n')
        cleaned = []
        prev_line_empty = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines between list items
            if not stripped and cleaned and cleaned[-1].strip().startswith('-'):
                continue
                
            # Skip consecutive empty lines
            if not stripped and prev_line_empty:
                continue
                
            cleaned.append(line)
            prev_line_empty = not stripped
            
        # Ensure exactly one newline at end
        return '\n'.join(cleaned).strip() 
        
    def _parse_for_block(self, block: str) -> tuple:
        """Parse a for block into loop variable and iterable parts."""
        parts = block[4:].split(' in ', 1)
        return parts[0].strip(), parts[1].strip()
        
    def _get_iterable(self, iterable: str, context: Dict[str, Any]) -> List[Any]:
        """Get an iterable from context or evaluate expression."""
        if iterable in context:
            return context[iterable]
        try:
            if not self._is_safe_expression(iterable):
                raise ValueError("Potentially dangerous expression detected")
            
            safe_globals = self._get_safe_globals()
            return eval(iterable, safe_globals, context)
        except Exception:
            return []
            
    def _render_parts(self, parts: List[Union[str, None]], context: Dict[str, Any]) -> str:
        """Render a list of template parts with the given context."""
        temp_parser = TemplateParser('')
        temp_parser.compiled = parts
        return temp_parser.render(context)


# Example usage
if __name__ == '__main__':
    template = """
    <html>
    <body>
        <h1>Hello {{ name }}!</h1>
        
        {% if show_details %}
        <div class="details">
            <p>Your details:</p>
            <ul>
                {% for item in items %}
                <li>{{ item }}</li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}
    </body>
    </html>
    """
    
    context = {
        'name': 'World',
        'show_details': True,
        'items': ['Item 1', 'Item 2', 'Item 3']
    }
    
    parser = TemplateParser(template)
    result = parser.render(context)
    print(result)
    
    # 示例代码 - 自定义函数功能
    print("\n=== 自定义函数示例 ===")
    
    # 创建使用自定义函数的模板
    func_template = """
    {{= greet(name) }}
    {{= calculate(10, 20) }}
    {{= format_date(now) }}
    
    {% if 
        # 多行代码块示例
        user = context.get('user')
        premium = user.get('membership') == 'premium'
        active = user.get('is_active', False)
        __result__ = premium and active
    %}
    <p>Welcome premium user {{ user.name }}!</p>
    {% else %}
    <p>Welcome standard user {{ user.name }}!</p>
    {% endif %}
    
    {% if 
        # 带计算的代码块示例
        total = calculate(10, 20)
        discount = 0.2 if user.get('membership') == 'premium' else 0.1
        final_price = total * (1 - discount)
        __result__ = final_price > 15
    %}
    <p>Special discount applied! Final price: {{ final_price }}</p>
    {% endif %}
    """
    
    # 定义自定义函数
    def greet(name):
        return f"Hello, {name}!"
        
    def calculate(x, y):
        return x + y
        
    def format_date(dt):
        return dt.strftime("%Y-%m-%d")
        
    def is_premium_user(user):
        return user.get('membership') == 'premium'
    
    # 创建解析器并注册函数
    func_parser = TemplateParser(func_template)
    func_parser.register_function('greet', greet)
    func_parser.register_function('calculate', calculate)
    func_parser.register_function('format_date', format_date)
    func_parser.register_function('is_premium_user', is_premium_user)
    
    # 准备上下文
    from datetime import datetime
    func_context = {
        'name': 'Function User',
        'now': datetime.now(),
        'user': {
            'name': 'test_user',
            'membership': 'premium'  # 测试 premium 用户
        }
    }
    
    # 渲染并打印结果
    func_result = func_parser.render(func_context)
    print(func_result)